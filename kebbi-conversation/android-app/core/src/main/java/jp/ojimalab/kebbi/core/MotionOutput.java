package jp.ojimalab.kebbi.core;

import java.util.List;

/** Playback and lifecycle of the robot's motion service. */
public interface MotionOutput extends AutoCloseable {
  interface Events {
    void connected(boolean ready);

    void motions(List<String> names);

    void motionStarted(long token, String id);

    void motionDone(long token, String id, String error);
  }

  void connect(Events events);

  void play(long token, Motion motion);

  void refreshMotions();

  /** Stop motion and any other operation owned by the same device adapter. */
  void stopAll();

  /** Retire callback sources that belong to the finished turn. */
  void finishTurn();

  /** Release the current motion and retire its callbacks before the next sentence. */
  default void finishSentence() {
    stopAll();
  }

  @Override
  void close();
}
