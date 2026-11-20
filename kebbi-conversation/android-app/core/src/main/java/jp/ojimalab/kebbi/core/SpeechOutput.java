package jp.ojimalab.kebbi.core;

/** Plays one utterance. Synthesis can happen before playback inside the implementation. */
public interface SpeechOutput extends AutoCloseable {
  interface Listener {
    /** Playback has started, or the engine has reported its playback-start event. */
    void started();

    void completed(String error);
  }

  void speak(long token, String text, String language, Listener listener);

  /** Cancel synthesis and playback. Safe to call when idle. */
  void stopSpeaking();

  @Override
  void close();
}
