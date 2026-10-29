package jp.ojimalab.kebbi.core;

import java.util.List;

public interface RobotAdapter {
  interface Events {
    void connected(boolean ready);

    void motions(List<String> names);

    void asr(long token, String text, String error);

    void ttsStarted(long token);

    void ttsDone(long token, String error);

    void motionStarted(long token, String id);

    void motionDone(long token, String id, String error);
  }

  void connect(Events events);

  void listen(long token, String language);

  void stopListening();

  void speak(long token, String text, String language);

  void play(long token, Motion motion);

  void refreshMotions();

  void stopAll();

  /** Retire callback source before accepting a different real-device turn. */
  void finishTurn();

  /** Stop the sentence action and retire callbacks before a different sentence. */
  default void finishSentence() { stopAll(); }

  void close();

  default void configureMock(String input, String fault) {}
}
