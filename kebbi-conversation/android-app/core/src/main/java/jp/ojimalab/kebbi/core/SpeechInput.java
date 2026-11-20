package jp.ojimalab.kebbi.core;

/** One listening request. Each result belongs to the listener supplied for that request. */
public interface SpeechInput extends AutoCloseable {
  interface Listener {
    void complete(String text, String error);
  }

  void listen(long token, String language, Listener listener);

  /** Cancel recording and recognition. Safe to call when idle. */
  void stopListening();

  @Override
  void close();
}
