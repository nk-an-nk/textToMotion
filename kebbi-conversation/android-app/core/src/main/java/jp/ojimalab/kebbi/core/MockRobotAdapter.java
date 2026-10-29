package jp.ojimalab.kebbi.core;

import java.util.*;

public final class MockRobotAdapter implements RobotAdapter {
  private final RuntimePorts.Scheduler scheduler;
  private Events events;
  private long epoch;
  private String input = "Hello, Kebbi!", fault = "none";
  public static final List<String> MOTIONS = Arrays.asList("mock_wave", "mock_nod", "mock_praise");

  public MockRobotAdapter(RuntimePorts.Scheduler scheduler) {
    this.scheduler = scheduler;
  }

  public void configureMock(String input, String fault) {
    this.input = input;
    this.fault = fault;
  }

  public void connect(Events events) {
    this.events = events;
    events.connected(true);
    refreshMotions();
  }

  private void emit(long delay, Runnable action) {
    long captured = epoch;
    scheduler.later(
        delay,
        () -> {
          if (captured == epoch && events != null) action.run();
        });
  }

  public void listen(long token, String language) {
    if (fault.equals("asr_timeout")) return;
    String captured = input, error = fault.equals("asr_error") ? "asr_error" : null;
    emit(300, () -> events.asr(token, captured, error));
  }

  public void stopListening() {} // Turn tokens also reject any delayed ASR result.

  public void speak(long token, String text, String language) {
    emit(20, () -> events.ttsStarted(token));
    if (!fault.equals("tts_timeout"))
      emit(700, () -> events.ttsDone(token, fault.equals("tts_error") ? "tts_error" : null));
  }

  public void play(long token, Motion motion) {
    if (!MOTIONS.contains(motion.id)) {
      events.motionDone(token, motion.id, "motion_missing");
      return;
    }
    emit(25, () -> events.motionStarted(token, motion.id));
    if (!fault.equals("motion_timeout"))
      emit(
          1000,
          () ->
              events.motionDone(
                  token, motion.id, fault.equals("motion_error") ? "motion_error" : null));
  }

  public boolean supportsSentenceOutput() { return true; }

  public void refreshMotions() {
    if (events != null) events.motions(MOTIONS);
  }

  public void stopAll() {
    epoch++;
  }

  public void finishTurn() {
    epoch++;
  }

  public void close() {
    epoch++;
    events = null;
  }
}
