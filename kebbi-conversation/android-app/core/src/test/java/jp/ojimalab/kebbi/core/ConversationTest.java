package jp.ojimalab.kebbi.core;

import static jp.ojimalab.kebbi.core.RuntimePorts.*;
import static org.junit.Assert.*;

import java.util.*;
import org.junit.*;

public class ConversationTest {
  static class Clock implements Scheduler {
    long now;

    static class Task {
      long at;
      Runnable r;
      boolean canceled;

      Task(long at, Runnable r) {
        this.at = at;
        this.r = r;
      }
    }

    List<Task> tasks = new ArrayList<>();

    public long now() {
      return now;
    }

    public void execute(Runnable r) {
      r.run();
    }

    public Cancel later(long delay, Runnable r) {
      Task t = new Task(now + delay, r);
      tasks.add(t);
      return () -> t.canceled = true;
    }

    void advance(long ms) {
      long until = now + ms;
      while (true) {
        Task next =
            tasks.stream()
                .filter(t -> !t.canceled && t.at <= until)
                .min(Comparator.comparingLong(t -> t.at))
                .orElse(null);
        if (next == null) break;
        tasks.remove(next);
        now = next.at;
        next.r.run();
      }
      now = until;
    }
  }

  static class Robot implements RobotAdapter {
    Events e;
    long token;
    int speak, play, stop;

    public void connect(Events e) {
      this.e = e;
      e.connected(true);
      e.motions(Arrays.asList("mock_wave"));
    }

    public void listen(long t, String l) {
      token = t;
    }

    public void stopListening() {}

    public void speak(long t, String s, String l) {
      token = t;
      speak++;
    }

    public void play(long t, Motion m) {
      token = t;
      play++;
    }

    public void refreshMotions() {}

    public void stopAll() {
      stop++;
    }

    public void finishTurn() {}

    public void close() {}
  }

  static class Server implements Backend {
    Result result;
    boolean canceled;
    List<String> gestures;
    SelectionOptions options;

    public Cancel respond(String s, String t, String text, String l, List<String> g, Result r) {
      result = r;
      gestures = g;
      return () -> canceled = true;
    }

    public Cancel respond(String s, String t, String text, String l, SelectionOptions o, Result r) {
      options = o;
      return respond(s, t, text, l, o.gestures, r);
    }

    public void forget(String s) {}

    void reply() {
      result.success(new Reply("Hello!", Gesture.greet, "en"));
    }
  }

  Clock clock;
  Robot robot;
  Server server;
  ConversationController c;
  Snapshot snapshot;
  List<String> events;
  MotionRegistry registry;

  @Before
  public void setup() {
    clock = new Clock();
    robot = new Robot();
    server = new Server();
    events = new ArrayList<>();
    registry = MotionRegistry.parse("{\"greet\":[{\"id\":\"mock_wave\",\"cooldownMs\":5000}]}");
    c =
        new ConversationController(
            robot, server, clock, (t, n, f) -> events.add(n), s -> snapshot = s, registry);
    c.connect();
  }

  private void output() {
    c.submit("Hello");
    assertEquals(State.PROCESSING, c.state());
    server.reply();
    assertEquals(State.SPEAKING, c.state());
    assertEquals(1, robot.speak);
    assertEquals(1, robot.play);
  }

  @Test
  public void ttsThenMotion() {
    output();
    robot.e.ttsStarted(robot.token);
    robot.e.motionStarted(robot.token, "mock_wave");
    robot.e.ttsDone(robot.token, null);
    assertEquals(State.SPEAKING, c.state());
    robot.e.motionDone(robot.token, "mock_wave", null);
    assertEquals(State.IDLE, c.state());
    assertTrue(events.contains("metrics"));
  }

  @Test
  public void motionThenTts() {
    output();
    robot.e.motionDone(robot.token, "mock_wave", null);
    assertEquals(State.SPEAKING, c.state());
    robot.e.ttsDone(robot.token, null);
    assertEquals(State.IDLE, c.state());
  }

  @Test
  public void duplicateCallbacksAndLatePreviousTurn() {
    output();
    long old = robot.token;
    robot.e.ttsDone(old, null);
    robot.e.ttsDone(old, null);
    robot.e.motionDone(old, "wrong", null);
    assertEquals(State.SPEAKING, c.state());
    robot.e.motionDone(old, "mock_wave", null);
    c.submit("again");
    server.reply();
    robot.e.ttsDone(old, null);
    assertEquals(State.SPEAKING, c.state());
    robot.e.ttsDone(robot.token, null);
    assertEquals(State.IDLE, c.state());
  }

  @Test
  public void overlapRejected() {
    output();
    c.submit("again");
    c.listen(false);
    assertEquals(1, robot.speak);
    assertEquals(1, robot.play);
  }

  @Test
  public void cooldownAndUnavailableFallback() {
    output();
    robot.e.ttsDone(robot.token, null);
    robot.e.motionDone(robot.token, "mock_wave", null);
    c.submit("again");
    server.reply();
    assertEquals(1, robot.play);
    robot.e.ttsDone(robot.token, null);
    assertEquals(State.IDLE, c.state());
    assertNull(registry.select(Gesture.greet, Collections.emptySet(), 99999));
    clock.advance(5000);
    assertNotNull(
        registry.select(Gesture.greet, new HashSet<>(Arrays.asList("mock_wave")), clock.now()));
  }

  @Test
  public void timeoutReturnsIdleAndIgnoresDelayedCompletions() {
    output();
    long old = robot.token;
    clock.advance(45000);
    assertEquals(State.IDLE, c.state());
    assertTrue(robot.stop > 0);
    robot.e.ttsDone(old, null);
    assertEquals(State.IDLE, c.state());
  }

  @Test
  public void asrTimeoutAndEmptyAsr() {
    c.listen(false);
    clock.advance(15000);
    assertEquals(State.IDLE, c.state());
    c.listen(false);
    robot.e.asr(robot.token, "", null);
    assertEquals(State.IDLE, c.state());
  }

  @Test
  public void asrOnlyAndAsrConversation() {
    c.listen(true);
    robot.e.asr(robot.token, "Hello", null);
    assertEquals(State.IDLE, c.state());
    assertNull(server.result);
    c.listen(false);
    robot.e.asr(robot.token, "Hello", null);
    assertEquals(State.PROCESSING, c.state());
    server.reply();
    assertEquals(State.SPEAKING, c.state());
  }

  @Test
  public void backendCancellationAndTimeout() {
    c.submit("hi");
    c.stop();
    server.reply();
    assertEquals(State.IDLE, c.state());
    assertTrue(server.canceled);
    assertEquals(0, robot.speak);
    c.submit("hi");
    clock.advance(25000);
    assertEquals(State.IDLE, c.state());
  }

  @Test
  public void speechAndMotionOnly() {
    c.testSpeech("hello", Gesture.none, false);
    robot.e.ttsDone(robot.token, null);
    assertEquals(State.IDLE, c.state());
    c.testMotion("mock_wave");
    assertEquals(State.SPEAKING, c.state());
    robot.e.motionDone(robot.token, "mock_wave", null);
    assertEquals(State.IDLE, c.state());
  }

  @Test
  public void motionErrorFallsBackToSpeech() {
    output();
    robot.e.motionDone(robot.token, "mock_wave", "motion_error");
    assertEquals(State.SPEAKING, c.state());
    robot.e.ttsDone(robot.token, null);
    assertEquals(State.IDLE, c.state());
  }

  @Test
  public void ttsFailureAndDisconnectRecover() {
    output();
    robot.e.ttsDone(robot.token, "tts_error");
    assertEquals(State.IDLE, c.state());
    c.submit("again");
    server.reply();
    robot.e.connected(false);
    assertEquals(State.IDLE, c.state());
    assertFalse(snapshot.connected);
  }

  @Test
  public void enabledAndMultipleCandidates() {
    Motion m = new Motion("other");
    registry.assign(Gesture.greet, m);
    Motion first = registry.entries(Gesture.greet).get(0);
    first.enabled = false;
    assertEquals(
        "other",
        registry.select(Gesture.greet, new HashSet<>(Arrays.asList("mock_wave", "other")), 0).id);
    assertNull(registry.select(Gesture.none, new HashSet<>(Arrays.asList("other")), 0));
    assertEquals(2, MotionRegistry.parse(registry.json()).entries(Gesture.greet).size());
  }

  @Test
  public void unknownGestureIsNone() {
    assertEquals(
        Gesture.none,
        Reply.parse(
                "{\"speech\":\"Hi\",\"gesture\":\"invented\",\"language\":\"en\",\"timing\":\"speech_start\"}")
            .gesture);
  }

  @Test
  public void invalidResponsesRejected() {
    for (String json :
        Arrays.asList(
            "{}",
            "{\"speech\":8,\"gesture\":\"greet\",\"language\":\"en\",\"timing\":\"speech_start\"}",
            "{\"speech\":\"Hi\",\"gesture\":\"greet\",\"language\":\"en\",\"timing\":\"later\"}")) {
      try {
        Reply.parse(json);
        fail("must reject");
      } catch (RuntimeException expected) {
      }
    }
  }

  @Test
  public void mockEndToEnd() {
    MockRobotAdapter mock = new MockRobotAdapter(clock);
    Backend immediate =
        new Backend() {
          public Cancel respond(String s, String t, String x, String l, List<String> g, Result r) {
            r.success(new Reply("Hello!", Gesture.greet, l));
            return () -> {};
          }

          public void forget(String s) {}
        };
    ConversationController app =
        new ConversationController(
            mock, immediate, clock, (t, n, f) -> events.add(n), s -> snapshot = s, registry);
    app.connect();
    app.submit("Hello Kebbi");
    assertEquals(State.SPEAKING, app.state());
    clock.advance(750);
    assertEquals(State.SPEAKING, app.state());
    clock.advance(300);
    assertEquals(State.IDLE, app.state());
    assertTrue(snapshot.ttsDone && snapshot.motionDone);
    assertTrue(
        events.contains("tts_start_notification")
            && events.contains("motion_start_notification")
            && events.contains("metrics"));
  }

  @Test public void directSelectsOnlyOfferedRegisteredId() {
    c.experiment("direct", "basic");
    c.submit("Hello");
    assertEquals("direct", server.options.mode);
    assertEquals("mock_wave", server.options.motions.get(0).id);
    server.result.success(new Reply("Hi!", Gesture.none, "en", "mock_wave"));
    assertEquals(1, robot.play);
    assertEquals("mock_wave", snapshot.motion);
  }

  @Test public void directDoesNotFallBackToCategoryForInventedId() {
    c.experiment("direct", "basic");
    c.submit("Hello");
    server.result.success(new Reply("Hi!", Gesture.greet, "en", "invented"));
    assertEquals(0, robot.play);
    assertEquals(1, robot.speak);
  }

  @Test public void directRevalidatesAvailabilityAfterNetworkResponse() {
    c.experiment("direct", "basic");
    c.submit("Hello");
    robot.e.motions(Collections.emptyList());
    server.result.success(new Reply("Hi!", Gesture.none, "en", "mock_wave"));
    assertEquals(0, robot.play);
  }

  @Test public void directCannotPlayNewlyRegisteredButUnofferedId() {
    c.experiment("direct", "basic");
    c.submit("Hello");
    registry.assign(Gesture.greet, new Motion("other"));
    robot.e.motions(Arrays.asList("mock_wave", "other"));
    server.result.success(new Reply("Hi!", Gesture.none, "en", "other"));
    assertEquals(0, robot.play);
  }

  @Test public void candidatesRespectDisableAndCooldownAcrossModes() {
    Motion m = registry.entries(Gesture.greet).get(0);
    registry.started(m, 0);
    assertTrue(registry.candidates(c.motions(), 1000).isEmpty());
    assertEquals(1, registry.candidates(c.motions(), 5000).size());
    m.enabled = false;
    assertTrue(registry.candidates(c.motions(), 5000).isEmpty());
    assertNull(registry.selectId(m.id, c.motions(), 5000));
  }

  @Test public void expandedProfileOffersMoreCategoriesAndDisabledMotionOffersNone() {
    registry.assign(Gesture.empathy, new Motion("mock_wave"));
    c.submit("sad");
    assertFalse(server.options.gestures.contains("empathy"));
    c.stop();
    c.experiment("category", "expanded");
    c.submit("sad");
    assertTrue(server.options.gestures.contains("empathy"));
    c.stop();
    c.settings("en", false);
    c.submit("Hello");
    assertEquals(Collections.singletonList("none"), server.options.gestures);
    assertTrue(server.options.motions.isEmpty());
  }

  @Test public void categoryIgnoresDirectMotionFieldAndReplyParserAcceptsNull() {
    c.submit("Hello");
    server.result.success(new Reply("Hi!", Gesture.none, "en", "mock_wave"));
    assertEquals(0, robot.play);
    Reply r = Reply.parse("{\"speech\":\"Hi\",\"gesture\":\"none\",\"language\":\"en\",\"timing\":\"speech_start\",\"motion_id\":null}");
    assertNull(r.motionId);
  }
}
