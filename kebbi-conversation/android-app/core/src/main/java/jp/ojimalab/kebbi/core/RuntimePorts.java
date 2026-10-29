package jp.ojimalab.kebbi.core;

import java.util.*;

public final class RuntimePorts {
  private RuntimePorts() {}

  public interface Cancel {
    void cancel();
  }

  public interface Scheduler {
    long now();

    void execute(Runnable action);

    Cancel later(long delayMs, Runnable action);
  }

  public interface Log {
    void event(String turnId, String name, Map<String, Object> fields);
  }

  public interface Backend {
    interface Result {
      void success(Reply reply);

      void failure(String code);
    }

    Cancel respond(
        String session,
        String turn,
        String text,
        String language,
        List<String> gestures,
        Result result);

    default Cancel respond(String session, String turn, String text, String language,
        SelectionOptions options, Result result) {
      return respond(session, turn, text, language, options.gestures, result);
    }

    void forget(String session);
  }

  public interface View {
    void render(Snapshot snapshot);
  }

  public enum State {
    IDLE,
    LISTENING,
    PROCESSING,
    SPEAKING,
    ERROR
  }

  public static final class Snapshot {
    public State state;
    public boolean connected, ttsDone, motionDone;
    public String text, speech, motion, message, turnId;
    public Gesture gesture;
  }
}
