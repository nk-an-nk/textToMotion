package jp.ojimalab.kebbi.core;

import static jp.ojimalab.kebbi.core.RuntimePorts.*;

import java.util.*;

/** All mutable state is confined to the supplied UI scheduler. */
public final class ConversationController implements RobotAdapter.Events {
  private final RobotAdapter robot;
  private final Backend backend;
  private final Scheduler scheduler;
  private final Log log;
  private final View view;
  private final MotionRegistry registry;
  private State state = State.IDLE;
  private boolean ready,
      asrOnly,
      ttsDone = true,
      motionDone = true,
      ttsStarted,
      motionStarted,
      closed;
  private long token, turnStart;
  private String session = UUID.randomUUID().toString(),
      turn = "",
      text = "",
      speech = "",
      motion = "",
      message = "",
      language = "en";
  private Gesture gesture = Gesture.none;
  private boolean motionEnabled = true;
  private final Set<String> available = new TreeSet<>();
  private final Map<String, Long> times = new LinkedHashMap<>();
  private Cancel timer = () -> {}, request = () -> {};

  public ConversationController(
      RobotAdapter robot,
      Backend backend,
      Scheduler scheduler,
      Log log,
      View view,
      MotionRegistry registry) {
    this.robot = robot;
    this.backend = backend;
    this.scheduler = scheduler;
    this.log = log;
    this.view = view;
    this.registry = registry;
  }

  public void connect() {
    if (!closed)
      try {
        robot.connect(this);
      } catch (RuntimeException error) {
        ready = false;
        message = "sdk_connection_error";
        publish();
      }
  }

  public void settings(String language, boolean motionEnabled) {
    if (!language.equals("en") && !language.equals("ja")) throw new IllegalArgumentException();
    this.language = language;
    this.motionEnabled = motionEnabled;
  }

  public Set<String> motions() {
    return Collections.unmodifiableSet(available);
  }

  public State state() {
    return state;
  }

  private void publish() {
    Snapshot s = new Snapshot();
    s.state = state;
    s.connected = ready;
    s.ttsDone = ttsDone;
    s.motionDone = motionDone;
    s.text = text;
    s.speech = speech;
    s.motion = motion;
    s.message = message;
    s.turnId = turn;
    s.gesture = gesture;
    view.render(s);
  }

  private void event(String name) {
    long now = scheduler.now();
    times.putIfAbsent(name, now);
    Map<String, Object> fields = new LinkedHashMap<>();
    fields.put("elapsed_ms", now - turnStart);
    log.event(turn, name, fields);
  }

  private void metric(Map<String, Object> values, String key, String from, String to) {
    if (times.containsKey(from) && times.containsKey(to))
      values.put(key, times.get(to) - times.get(from));
  }

  private void deadline(long delay, State expected) {
    timer.cancel();
    long current = token;
    timer =
        scheduler.later(
            delay,
            () -> {
              if (current == token && state == expected)
                fail(expected.name().toLowerCase() + "_timeout");
            });
  }

  private boolean begin() {
    if (closed || !ready || state != State.IDLE) return false;
    token++;
    turn = UUID.randomUUID().toString();
    turnStart = scheduler.now();
    times.clear();
    text = "";
    speech = "";
    motion = "";
    message = "";
    gesture = Gesture.none;
    ttsDone = true;
    motionDone = true;
    ttsStarted = false;
    motionStarted = false;
    event("turn_start");
    return true;
  }

  public void listen(boolean only) {
    if (!begin()) return;
    asrOnly = only;
    state = State.LISTENING;
    publish();
    event("asr_start");
    deadline(15000, State.LISTENING);
    try {
      robot.listen(token, language);
    } catch (RuntimeException error) {
      fail("asr_error");
    }
  }

  public void submit(String input) {
    if (input == null || input.trim().isEmpty() || input.length() > 1000) {
      message = "invalid_text";
      publish();
      return;
    }
    if (!begin()) return;
    text = input.trim();
    process();
  }

  private void process() {
    timer.cancel();
    try {
      robot.stopListening();
    } catch (RuntimeException error) {
      fail("asr_stop_error");
      return;
    }
    state = State.PROCESSING;
    event("llm_request_start");
    publish();
    deadline(25000, State.PROCESSING);
    long current = token;
    try {
      request =
          backend.respond(
              session,
              turn,
              text,
              language,
              motionEnabled
                  ? registry.availableGestures(available)
                  : Collections.singletonList("none"),
              new Backend.Result() {
                public void success(Reply reply) {
                  scheduler.execute(
                      () -> {
                        if (current != token || state != State.PROCESSING) return;
                        event("llm_response_received");
                        output(reply.speech, reply.gesture, reply.language, null);
                      });
                }

                public void failure(String code) {
                  scheduler.execute(
                      () -> {
                        if (current == token && state == State.PROCESSING) fail(code);
                      });
                }
              });
    } catch (RuntimeException error) {
      fail("backend_error");
    }
  }

  public void testSpeech(String input, Gesture g, boolean withMotion) {
    if (input == null || input.trim().isEmpty() || input.length() > 400) return;
    if (begin()) output(input, withMotion ? g : Gesture.none, language, null);
  }

  public void testMotion(String id) {
    if (!available.contains(id) || !begin()) return;
    Motion m = registry.find(id);
    if (!registry.eligible(m, scheduler.now())) {
      message = "motion_cooldown";
      finish();
      return;
    }
    output("", Gesture.none, language, m);
  }

  private void output(String utterance, Gesture category, String lang, Motion forced) {
    timer.cancel();
    try {
      robot.stopListening();
    } catch (RuntimeException error) {
      fail("asr_stop_error");
      return;
    }
    speech = utterance;
    gesture = category;
    Motion selected =
        forced != null
            ? forced
            : (motionEnabled ? registry.select(category, available, scheduler.now()) : null);
    motion = selected == null ? "" : selected.id;
    ttsDone = speech.isEmpty();
    motionDone = selected == null;
    state = State.SPEAKING;
    publish();
    deadline(45000, State.SPEAKING);
    long current = token;
    try {
      // Flags are initialized before either API call, so synchronous callbacks are safe.
      if (!ttsDone) {
        event("tts_request");
        robot.speak(current, speech, lang);
      }
      if (current != token || state != State.SPEAKING) return;
      if (selected != null) {
        registry.started(selected, scheduler.now());
        event("motion_request");
        robot.play(current, selected);
      }
      if (current == token) completeIfDone();
    } catch (RuntimeException error) {
      fail("robot_command_error");
    }
  }

  private boolean accepts(long current, State expected) {
    return !closed && current == token && state == expected;
  }

  public void connected(boolean connected) {
    scheduler.execute(
        () -> {
          if (closed) return;
          ready = connected;
          if (!ready && state != State.IDLE) fail("sdk_disconnected");
          else publish();
        });
  }

  public void motions(List<String> names) {
    scheduler.execute(
        () -> {
          if (closed) return;
          available.clear();
          available.addAll(names);
          publish();
        });
  }

  public void asr(long current, String result, String error) {
    scheduler.execute(
        () -> {
          if (!accepts(current, State.LISTENING)) return;
          event("asr_complete");
          try {
            robot.stopListening();
          } catch (RuntimeException failure) {
            fail("asr_stop_error");
            return;
          }
          if (error != null) {
            fail(error);
            return;
          }
          if (result == null || result.trim().isEmpty() || result.length() > 1000) {
            fail("asr_empty_or_long");
            return;
          }
          text = result.trim();
          if (asrOnly) finish();
          else process();
        });
  }

  public void ttsStarted(long current) {
    scheduler.execute(
        () -> {
          if (accepts(current, State.SPEAKING) && !ttsDone && !ttsStarted) {
            ttsStarted = true;
            event("tts_start_notification");
          }
        });
  }

  public void ttsDone(long current, String error) {
    scheduler.execute(
        () -> {
          if (!accepts(current, State.SPEAKING) || ttsDone) return;
          event("tts_complete");
          if (error != null) {
            fail(error);
            return;
          }
          ttsDone = true;
          publish();
          completeIfDone();
        });
  }

  public void motionStarted(long current, String id) {
    scheduler.execute(
        () -> {
          if (accepts(current, State.SPEAKING)
              && motion.equals(id)
              && !motionDone
              && !motionStarted) {
            motionStarted = true;
            event("motion_start_notification");
          }
        });
  }

  public void motionDone(long current, String id, String error) {
    scheduler.execute(
        () -> {
          if (!accepts(current, State.SPEAKING) || motionDone || !motion.equals(id)) return;
          event("motion_complete");
          motionDone = true;
          if (error != null) {
            message = error;
            event("motion_error");
          }
          publish();
          completeIfDone();
        });
  }

  private void completeIfDone() {
    if (state == State.SPEAKING && ttsDone && motionDone) finish();
  }

  private void finish() {
    timer.cancel();
    event("turn_complete");
    Map<String, Object> values = new LinkedHashMap<>();
    values.put("turn_ms", scheduler.now() - turnStart);
    metric(values, "asr_ms", "asr_start", "asr_complete");
    metric(values, "llm_ms", "llm_request_start", "llm_response_received");
    metric(values, "speech_latency_ms", "turn_start", "tts_start_notification");
    metric(values, "motion_latency_ms", "turn_start", "motion_start_notification");
    metric(values, "speech_request_latency_ms", "turn_start", "tts_request");
    metric(values, "motion_request_latency_ms", "turn_start", "motion_request");
    metric(values, "request_start_difference_ms", "tts_request", "motion_request");
    metric(values, "start_difference_ms", "tts_start_notification", "motion_start_notification");
    log.event(turn, "metrics", values);
    token++;
    state = State.IDLE;
    ttsDone = true;
    motionDone = true;
    try {
      robot.finishTurn();
    } catch (RuntimeException ignored) {
      ready = false;
      message = "sdk_reset_error";
    }
    publish();
  }

  private void fail(String code) {
    message = code;
    state = State.ERROR;
    event("error");
    log.event(turn, "error_detail", Collections.singletonMap("code", code));
    publish();
    stop();
  }

  public void stop() {
    token++;
    timer.cancel();
    request.cancel();
    state = State.IDLE;
    ttsDone = true;
    motionDone = true;
    try {
      robot.stopAll();
    } catch (RuntimeException ignored) {
      ready = false;
    }
    event("stopped");
    publish();
  }

  public void newSession() {
    stop();
    backend.forget(session);
    session = UUID.randomUUID().toString();
    text = "";
    speech = "";
    message = "";
    motion = "";
    publish();
  }

  public void close() {
    if (closed) return;
    stop();
    closed = true;
    robot.close();
    backend.forget(session);
  }
}
