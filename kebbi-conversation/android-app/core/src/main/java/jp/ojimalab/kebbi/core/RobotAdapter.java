package jp.ojimalab.kebbi.core;

/** A device that exposes all three capabilities over one connection. */
public interface RobotAdapter extends SpeechInput, SpeechOutput, MotionOutput {
  /** Used when this adapter supplies both motion and speech output. */
  default boolean supportsSentenceOutput() { return false; }

  default void outputSentence(long token, Motion motion, String text, String language,
      SpeechOutput.Listener listener) {
    play(token, motion);
    speak(token, text, language, listener);
  }

  default void configureMock(String input, String fault) {}
}
