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
    int speak, play, stop, listens;
    String listenLanguage, speakLanguage;

    public void connect(Events e) {
      this.e = e;
      e.connected(true);
      e.motions(Arrays.asList("mock_wave"));
    }

    public void listen(long t, String l) {
      listens++;
      listenLanguage = l;
      token = t;
    }

    public void stopListening() {}

    public void speak(long t, String s, String l) {
      speakLanguage = l;
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
    List<String> sessions=new ArrayList<>();

    public Cancel respond(String s, String t, String text, String l, List<String> g, Result r) {
      sessions.add(s);
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
    // Category disable applies to that mapping; direct mode covers every SDK ID.
    assertNull(registry.select(Gesture.greet, c.motions(), 5000));
    assertEquals(1, registry.candidates(c.motions(), 5000).size());
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

  @Test public void entireSdkCatalogIsOfferedWithoutManualRegistration() {
    List<String> names = new ArrayList<>();
    names.add("000_A1_SHand_B2");
    for (int i = 0; i < 300; i++) names.add("motion_" + i);
    names.add("sadnessL_Sad");
    robot.e.motions(names);
    c.experiment("direct", "basic");
    c.submit("I am sad");
    assertEquals(302, server.options.motions.size());
    assertTrue(server.options.motions.stream().anyMatch(m -> m.id.equals("sadnessL_Sad")));
    server.result.success(new Reply("I hear you.", Gesture.none, "en", "sadnessL_Sad"));
    assertEquals(1, robot.play);
    assertEquals("sadnessL_Sad", snapshot.motion);
  }

  @Test public void categoryDoesNotTransmitFullCatalogAndLocallyRotatesCandidates() {
    Motion other = new Motion("other"); registry.assign(Gesture.greet, other);
    Set<String> available = new HashSet<>(Arrays.asList("mock_wave", "other"));
    assertEquals("mock_wave", registry.select(Gesture.greet, available, 0).id);
    registry.started(registry.find("mock_wave"), 0);
    assertEquals("other", registry.select(Gesture.greet, available, 6000).id);
    c.submit("Hello");
    assertTrue(server.options.motions.isEmpty());
  }

  @Test public void timingDefinitionsAndCancelledAttemptsAreRecordedOnce() {
    List<Map<String,Object>> recorded = new ArrayList<>();
    ConversationController app = new ConversationController(robot, server, clock,
        (t,n,f) -> { if (n.equals("metrics")) recorded.add(new LinkedHashMap<>(f)); },
        s -> {}, registry);
    app.connect(); app.listen(false); clock.advance(3000);
    robot.e.asr(robot.token, "Hello", null); clock.advance(1000); server.reply();
    clock.advance(200); robot.e.ttsStarted(robot.token);
    clock.advance(800); robot.e.ttsDone(robot.token, null); robot.e.motionDone(robot.token, "mock_wave", null);
    assertEquals(1, recorded.size());
    assertEquals(1000L, recorded.get(0).get("llm_ms"));
    assertEquals(1200L, recorded.get(0).get("reply_latency_ms"));
    assertEquals(4200L, recorded.get(0).get("speech_latency_ms"));
    assertEquals("conversation_voice", recorded.get(0).get("input_mode"));
    app.submit("again"); clock.advance(500); app.stop(); app.stop(); app.close();
    assertEquals(2, recorded.size());
    assertEquals("cancelled", recorded.get(1).get("status"));
    assertFalse(recorded.get(1).containsKey("reply_latency_ms"));
  }

  @Test public void expandedTaxonomyExcludesCoarseProfileAliases() {
    Motion alias=new Motion("other"); alias.basicOnly=true; registry.assign(Gesture.greet,alias);
    Set<String> available=new HashSet<>(Arrays.asList("other"));
    assertNotNull(registry.select(Gesture.greet,available,0,false));
    assertNull(registry.select(Gesture.greet,available,0,true));
    assertFalse(registry.availableGestures(available,0,true).contains("greet"));
  }

  @Test public void japaneseSelectionReachesRecognitionAndSpeech() {
    c.settings("ja", true); c.listen(false);
    assertEquals("ja", robot.listenLanguage);
    robot.e.asr(robot.token, "こんにちは", null);
    server.result.success(new Reply("こんにちは！", Gesture.greet, "ja"));
    assertEquals("ja", robot.speakLanguage);
  }

  private Reply twoSentencePlan() {
    return new Reply("Hello. How are you?",Gesture.greet,"en",null,Arrays.asList(
      new Reply.Sentence("Hello.",Gesture.greet,null),
      new Reply.Sentence("How are you?",Gesture.question,null)));
  }

  @Test public void eachSentenceWaitsForMotionStartBeforeSpeechAndRetiresOldCallbacks() {
    registry.assign(Gesture.question,new Motion("other"));
    robot.e.motions(Arrays.asList("mock_wave","other"));
    c.submit("Hello");server.result.success(twoSentencePlan());
    long first=robot.token;
    assertEquals(0,robot.speak);assertEquals(1,robot.play);
    clock.advance(2300);assertEquals(0,robot.speak);
    robot.e.motionStarted(first,"mock_wave");robot.e.motionStarted(first,"mock_wave");
    assertEquals(1,robot.speak);robot.e.ttsStarted(first);
    robot.e.ttsDone(first,null);
    assertEquals(1,robot.stop);assertEquals(1,robot.speak);
    clock.advance(80);
    long second=robot.token;assertNotEquals(first,second);
    assertEquals(1,robot.speak);assertEquals(2,robot.play);
    robot.e.ttsDone(first,null);robot.e.motionDone(first,"mock_wave",null);
    assertEquals(State.SPEAKING,c.state());
    robot.e.motionStarted(second,"other");assertEquals(2,robot.speak);robot.e.ttsStarted(second);
    robot.e.ttsDone(second,null);
    assertEquals(State.IDLE,c.state());assertEquals(2,robot.stop);
    assertEquals(2,Collections.frequency(events,"sentence_complete"));
  }

  @Test public void missingMotionStartTimesOutWithoutSpeakingOutOfSync() {
    c.submit("Hello");server.result.success(twoSentencePlan());
    assertEquals(1,robot.play);assertEquals(0,robot.speak);
    clock.advance(8000);
    assertEquals(State.IDLE,c.state());assertEquals("motion_start_timeout",snapshot.message);
    assertEquals(0,robot.speak);
  }

  @Test public void continuousConversationKeepsSessionAndStopPreventsNextListening() {
    c.startConversation();assertEquals(State.LISTENING,c.state());
    robot.e.asr(robot.token,"I like pandas",null);server.reply();
    robot.e.ttsDone(robot.token,null);robot.e.motionDone(robot.token,"mock_wave",null);
    assertEquals(State.IDLE,c.state());clock.advance(699);assertEquals(1,robot.listens);
    clock.advance(1);assertEquals(State.LISTENING,c.state());assertEquals(2,robot.listens);
    robot.e.asr(robot.token,"Black and white",null);
    assertEquals(2,server.sessions.size());assertEquals(server.sessions.get(0),server.sessions.get(1));
    c.stop();clock.advance(60000);
    assertEquals(State.IDLE,c.state());assertEquals(2,robot.listens);assertFalse(snapshot.continuous);
  }

  @Test public void noListeningBetweenSentencesAndSilenceRearmsUntilStop() {
    c.startConversation();robot.e.asr(robot.token,"Hello",null);server.result.success(twoSentencePlan());
    robot.e.motionStarted(robot.token,"mock_wave");robot.e.ttsStarted(robot.token);robot.e.ttsDone(robot.token,null);clock.advance(80);
    assertEquals(1,robot.listens);assertEquals(State.SPEAKING,c.state());
    robot.e.ttsStarted(robot.token);robot.e.ttsDone(robot.token,null);
    clock.advance(700);assertEquals(2,robot.listens);assertEquals(State.LISTENING,c.state());
    clock.advance(15000);clock.advance(700);assertEquals(3,robot.listens);
    c.stop();clock.advance(60000);assertEquals(3,robot.listens);
  }

  @Test public void stopDuringSentenceReconnectCancelsPendingSecondSentence() {
    c.submit("Hello");server.result.success(twoSentencePlan());
    robot.e.motionStarted(robot.token,"mock_wave");robot.e.ttsStarted(robot.token);robot.e.ttsDone(robot.token,null);
    c.stop();robot.e.connected(true);clock.advance(20000);
    assertEquals(1,robot.speak);assertEquals(State.IDLE,c.state());
  }

  @Test public void sentenceParserChecksFullReplyAndPerSentenceFields() {
    String json="{\"speech\":\"Hello. How are you?\",\"gesture\":\"greet\",\"language\":\"en\",\"timing\":\"speech_start\",\"sentences\":[{\"speech\":\"Hello.\",\"gesture\":\"greet\"},{\"speech\":\"How are you?\",\"gesture\":\"question\"}]}";
    Reply r=Reply.parse(json);assertTrue(r.sentencePlan);assertEquals(2,r.sentences.size());
    try { Reply.parse(json.replace("Hello. How are you?","Mismatch"));fail(); }
    catch (IllegalArgumentException expected) {}
  }

  static class FastRobot extends Robot {
    public boolean supportsSentenceOutput() { return true; }
  }

  @Test public void fastSentenceDispatchesSpeechWithoutWaitingForMotionStartAndHasShortGap() {
    FastRobot fast=new FastRobot();
    registry.assign(Gesture.question,new Motion("other"));
    ConversationController app=new ConversationController(fast,server,clock,(t,n,f)->{},s->{},registry);
    app.connect();fast.e.motions(Arrays.asList("mock_wave","other"));
    app.submit("Hello");server.result.success(twoSentencePlan());
    assertEquals(1,fast.play);assertEquals(1,fast.speak);
    long first=fast.token;
    fast.e.ttsStarted(first);fast.e.ttsDone(first,null);
    clock.advance(9);assertEquals(1,fast.speak);
    clock.advance(1);assertEquals(2,fast.speak);assertEquals(2,fast.play);
    long second=fast.token;
    fast.e.ttsDone(first,null);assertEquals(State.SPEAKING,app.state());
    fast.e.ttsStarted(second);fast.e.ttsDone(second,null);
    assertEquals(State.IDLE,app.state());
  }

  @Test public void stopCancelsTheShortFastSentenceTransition() {
    FastRobot fast=new FastRobot();
    ConversationController app=new ConversationController(fast,server,clock,(t,n,f)->{},s->{},registry);
    app.connect();app.submit("Hello");server.result.success(twoSentencePlan());
    fast.e.ttsStarted(fast.token);fast.e.ttsDone(fast.token,null);
    app.stop();clock.advance(1000);
    assertEquals(1,fast.speak);assertEquals(State.IDLE,app.state());
  }
}
