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
  private boolean turnActive;
  private String inputMode = "";
  private boolean playingPlan, waitingForSentence, continuous, autoPending;
  private int sentenceIndex=-1, asrErrors;
  private String currentSentence="";
  private List<Reply.Sentence> sentences=Collections.emptyList();
  private SelectionOptions planOptions;
  private Motion pendingMotion;
  private boolean sentenceSpeechRequested;
  private Cancel motionStartWait=()->{};
  private final Map<String,Long> sentenceTimes=new LinkedHashMap<>();
  private final List<String> motionRequests=new ArrayList<>();
  private Cancel autoTimer=()->{}, sentenceResume=()->{};
  private String session = UUID.randomUUID().toString(),
      turn = "",
      text = "",
      speech = "",
      motion = "",
      message = "",
      language = "en";
  private Gesture gesture = Gesture.none;
  private boolean motionEnabled = true;
  private String selectionMode = "category", gestureProfile = "basic";

  public void experiment(String mode, String profile) {
    new SelectionOptions(mode, profile, Collections.emptyList(), Collections.emptyList());
    if (state != State.IDLE) throw new IllegalStateException("turn_active");
    if (!selectionMode.equals(mode) || !gestureProfile.equals(profile)) newSession();
    selectionMode = mode;
    gestureProfile = profile;
  }
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
    s.continuous=continuous;
    s.sentenceIndex=sentenceIndex;
    s.sentenceCount=sentences.size();
    s.currentSentence=currentSentence;
    view.render(s);
  }

  private void event(String name) {
    long now = scheduler.now();
    times.putIfAbsent(name, now);
    if (playingPlan) sentenceTimes.putIfAbsent(name, now);
    Map<String, Object> fields = new LinkedHashMap<>();
    fields.put("elapsed_ms", now - turnStart);
    fields.put("selection_mode", selectionMode);
    fields.put("gesture_profile", gestureProfile);
    if (playingPlan) { fields.put("sentence_index", sentenceIndex+1); fields.put("sentence_count", sentences.size()); }
    if (!motion.isEmpty()) fields.put("motion_id",motion);
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

  private boolean begin(String kind) {
    if (closed || !ready || state != State.IDLE) return false;
    autoTimer.cancel();autoPending=false;
    playingPlan=false;waitingForSentence=false;sentenceIndex=-1;currentSentence="";
    sentences=Collections.emptyList();pendingMotion=null;motionRequests.clear();
    turnActive = true;
    inputMode = kind;
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

  public void startConversation() {
    if (closed || !ready || state!=State.IDLE) return;
    continuous=true;asrErrors=0;listen(false);
  }

  private void scheduleListening() {
    if (!continuous || closed || !ready || state!=State.IDLE || autoPending) return;
    autoPending=true;long captured=token;
    autoTimer=scheduler.later(700,()->{
      autoPending=false;
      if (captured==token && continuous && ready && !closed && state==State.IDLE) listen(false);
    });
  }

  public void listen(boolean only) {
    if (!begin(only ? "asr_only" : "conversation_voice")) return;
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
    if (!begin("conversation_text")) return;
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
    List<String> labels = new ArrayList<>(motionEnabled ? registry.availableGestures(available, scheduler.now(), gestureProfile.equals("expanded"))
        : Collections.singletonList("none"));
    if (gestureProfile.equals("basic")) labels.removeIf(g -> !Gesture.basic(Gesture.safe(g)));
    // Use a mutable copy before filtering even when motion is disabled.
    SelectionOptions options = new SelectionOptions(selectionMode, gestureProfile, labels,
        motionEnabled && selectionMode.equals("direct") ? registry.candidates(available, scheduler.now()) : Collections.emptyList());
    try {
      request =
          backend.respond(
              session,
              turn,
              text,
              language,
              options,
              new Backend.Result() {
                public void success(Reply reply) {
                  scheduler.execute(
                      () -> {
                        if (current != token || state != State.PROCESSING) return;
                        event("llm_response_received");
                        if (reply.sentencePlan) { startPlan(reply, options); return; }
                        boolean direct = options.mode.equals("direct");
                        boolean offered = options.motions.stream().anyMatch(m -> m.id.equals(reply.motionId));
                        Motion selected = direct && offered && motionEnabled
                            ? registry.selectId(reply.motionId, available, scheduler.now()) : null;
                        Gesture category = !direct && options.gestures.contains(reply.gesture.name())
                            ? reply.gesture : Gesture.none;
                        Map<String, Object> selection = new LinkedHashMap<>();
                        selection.put("selection_mode", options.mode);
                        selection.put("gesture_profile", options.profile);
                        selection.put("gesture", category.name());
                        selection.put("requested_motion_id", reply.motionId);
                        selection.put("candidate_count", options.motions.size());
                        selection.put("fallback", direct && reply.motionId != null && selected == null);
                        log.event(turn, "llm_selection", selection);
                        output(reply.speech, category, reply.language, selected);
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
    if (begin(withMotion ? "tts_motion" : "tts_only")) output(input, withMotion ? g : Gesture.none, language, null);
  }

  public void testMotion(String id) {
    if (!available.contains(id) || !begin("motion_only")) return;
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
            : (motionEnabled ? registry.select(category, available, scheduler.now(), gestureProfile.equals("expanded")) : null);
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
        motionRequests.add(selected.id);
        robot.play(current, selected);
      }
      if (current == token) completeIfDone();
    } catch (RuntimeException error) {
      fail("robot_command_error");
    }
  }

  private void startPlan(Reply reply, SelectionOptions options) {
    sentences=reply.sentences;planOptions=options;playingPlan=true;sentenceIndex=0;
    speech=reply.speech;startSentence();
  }

  private void startSentence() {
    waitingForSentence=false;sentenceResume.cancel();timer.cancel();
    token++;sentenceTimes.clear();pendingMotion=null;
    Reply.Sentence item=sentences.get(sentenceIndex);
    currentSentence=item.speech;
    gesture=planOptions.mode.equals("category") && planOptions.gestures.contains(item.gesture.name()) ? item.gesture : Gesture.none;
    if (motionEnabled) {
      if (planOptions.mode.equals("direct")) {
        boolean offered=planOptions.motions.stream().anyMatch(m -> m.id.equals(item.motionId));
        if (offered && available.contains(item.motionId)) {
          Motion candidate=registry.find(item.motionId);
          if (candidate.valid() && (registry.eligible(candidate,scheduler.now()) || motionRequests.contains(candidate.id))) pendingMotion=candidate;
        }
      } else pendingMotion=registry.selectForSentence(gesture, available, scheduler.now(),gestureProfile.equals("expanded"),motionRequests);
    }
    motion=pendingMotion==null ? "" : pendingMotion.id;
    ttsDone=false;motionDone=pendingMotion==null;ttsStarted=false;motionStarted=false;sentenceSpeechRequested=false;
    state=State.SPEAKING;
    event("sentence_start");publish();deadline(45000,State.SPEAKING);
    if (pendingMotion==null) requestSentenceSpeech();
    else if (robot.supportsSentenceOutput()) {
      sentenceSpeechRequested=true;
      try {
        registry.started(pendingMotion,scheduler.now());motionRequests.add(pendingMotion.id);
        event("motion_request");event("tts_request");
        robot.outputSentence(token,pendingMotion,currentSentence,language);
      } catch (RuntimeException error) { fail("sentence_output_error"); }
    } else startSentenceMotion();
  }

  private void requestSentenceSpeech() {
    if (!playingPlan || sentenceSpeechRequested || state!=State.SPEAKING) return;
    sentenceSpeechRequested=true;motionStartWait.cancel();
    try { event("tts_request");robot.speak(token,currentSentence,language); }
    catch (RuntimeException error) { fail("tts_error"); }
  }

  private void startSentenceMotion() {
    if (pendingMotion==null || motionDone) return;
    try {
      registry.started(pendingMotion,scheduler.now());
      motionRequests.add(pendingMotion.id);
      event("motion_request");
      long captured=token;
      motionStartWait=scheduler.later(8000,()->{
        if (captured==token && playingPlan && !sentenceSpeechRequested) fail("motion_start_timeout");
      });
      robot.play(token,pendingMotion);
    } catch (RuntimeException error) {
      motionDone=true;message="motion_error";event("motion_error");motionStartWait.cancel();requestSentenceSpeech();
    }
  }

  private void finishSentence() {
    timer.cancel();motionStartWait.cancel();
    if (!motionDone) event(ttsStarted ? "sentence_motion_cutoff" : "sentence_motion_skipped");
    motionDone=true;event("sentence_complete");
    Map<String,Object> row=new LinkedHashMap<>();
    row.put("sentence_index",sentenceIndex+1);row.put("sentence_count",sentences.size());
    row.put("motion_id",motion);row.put("gesture",gesture.name());
    if (sentenceTimes.containsKey("tts_start_notification") && sentenceTimes.containsKey("motion_start_notification"))
      row.put("start_difference_ms",sentenceTimes.get("motion_start_notification")-sentenceTimes.get("tts_start_notification"));
    row.put("elapsed_ms",scheduler.now()-turnStart);log.event(turn,"sentence_metrics",row);
    if (sentenceIndex+1>=sentences.size()) { finish(true);return; }
    token++;sentenceIndex++;waitingForSentence=true;pendingMotion=null;
    long captured=token;
    timer=scheduler.later(10000,()->{ if (captured==token && waitingForSentence) fail("sentence_sdk_timeout"); });
    try { robot.finishSentence(); }
    catch (RuntimeException error) { fail("sentence_reset_error");return; }
    if (ready) scheduleSentence();
  }

  private void scheduleSentence() {
    sentenceResume.cancel();long captured=token;
    sentenceResume=scheduler.later(robot.supportsSentenceOutput()?10:80,()->{
      if (captured==token && waitingForSentence && ready && !closed && state==State.SPEAKING) startSentence();
    });
  }

  private boolean accepts(long current, State expected) {
    return !closed && current == token && state == expected;
  }

  public void connected(boolean connected) {
    scheduler.execute(
        () -> {
          if (closed) return;
          ready = connected;
          if (!ready && state != State.IDLE && !waitingForSentence) fail("sdk_disconnected");
          else {
            publish();
            if (ready && waitingForSentence) scheduleSentence();
            else scheduleListening();
          }
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
          if (result == null || result.trim().isEmpty()) {
            fail("asr_no_speech");
            return;
          }
          if (result.length() > 1000) {
            fail("asr_empty_or_long");
            return;
          }
          asrErrors=0;
          text = result.trim();
          if (asrOnly) finish();
          else process();
        });
  }

  public void ttsStarted(long current) {
    scheduler.execute(
        () -> {
          if (accepts(current, State.SPEAKING) && !ttsDone && !ttsStarted && (!playingPlan || sentenceSpeechRequested)) {
            ttsStarted = true;
            event("tts_start_notification");
          }
        });
  }

  public void ttsDone(long current, String error) {
    scheduler.execute(
        () -> {
          if (!accepts(current, State.SPEAKING) || ttsDone || (playingPlan && !sentenceSpeechRequested)) return;
          event("tts_complete");
          if (error != null) {
            fail(error);
            return;
          }
          ttsDone = true;
          if (playingPlan) {
            if (!ttsStarted) message="tts_start_notification_missing";
            finishSentence();
            return;
          }
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
            if (playingPlan) requestSentenceSpeech();
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
          if (playingPlan && !sentenceSpeechRequested) {
            motionStartWait.cancel();
            if (error==null) message="motion_start_notification_missing";
            requestSentenceSpeech();
          }
          publish();
          completeIfDone();
        });
  }

  private void completeIfDone() {
    if (state == State.SPEAKING && ttsDone && motionDone) finish();
  }

  private void finish() { finish(false); }

  private void finish(boolean endSentence) {
    timer.cancel();sentenceResume.cancel();motionStartWait.cancel();
    event("turn_complete");
    recordMetrics(message.isEmpty() ? "completed" : "partial", message);
    token++;
    state = State.IDLE;
    ttsDone = true;
    motionDone = true;
    playingPlan=false;waitingForSentence=false;
    try {
      if (endSentence) robot.finishSentence(); else robot.finishTurn();
    } catch (RuntimeException ignored) {
      ready = false;
      message = "sdk_reset_error";
    }
    publish();
    scheduleListening();
  }

  private void recordMetrics(String status, String code) {
    if (!turnActive) return;
    turnActive = false;
    Map<String, Object> values = new LinkedHashMap<>();
    values.put("status", status);
    values.put("error_code", code == null ? "" : code);
    values.put("input_mode", inputMode);
    values.put("language", language);
    values.put("sentence_count", sentences.isEmpty()?1:sentences.size());
    values.put("motion_ids", new ArrayList<>(motionRequests));
    values.put("selection_mode", selectionMode);
    values.put("gesture_profile", gestureProfile);
    values.put("gesture", gesture.name());
    values.put("motion_id", motion);
    values.put("turn_ms", scheduler.now() - turnStart);
    metric(values, "asr_ms", "asr_start", "asr_complete");
    metric(values, "llm_ms", "llm_request_start", "llm_response_received");
    metric(values, "speech_latency_ms", "turn_start", "tts_start_notification");
    metric(values, "reply_latency_ms", times.containsKey("asr_complete") ? "asr_complete" : "turn_start", "tts_start_notification");
    metric(values, "motion_latency_ms", "turn_start", "motion_start_notification");
    metric(values, "speech_request_latency_ms", "turn_start", "tts_request");
    metric(values, "motion_request_latency_ms", "turn_start", "motion_request");
    metric(values, "request_start_difference_ms", "tts_request", "motion_request");
    metric(values, "start_difference_ms", "tts_start_notification", "motion_start_notification");
    log.event(turn, "metrics", values);
  }

  private void fail(String code) {
    boolean retrySilence=continuous && state==State.LISTENING &&
        (code.equals("listening_timeout") || code.equals("asr_no_speech") ||
         (code.equals("asr_error") && ++asrErrors<3));
    message = code;
    state = State.ERROR;
    event("error");
    log.event(turn, "error_detail", Collections.singletonMap("code", code));
    recordMetrics("error", code);
    publish();
    stop();
    if (retrySilence) { continuous=true;scheduleListening();publish(); }
  }

  public void stop() {
    continuous=false;autoPending=false;waitingForSentence=false;playingPlan=false;
    autoTimer.cancel();sentenceResume.cancel();motionStartWait.cancel();pendingMotion=null;
    recordMetrics("cancelled", "user_or_lifecycle_stop");
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
