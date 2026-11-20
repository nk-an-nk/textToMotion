package jp.ojimalab.kebbi.ui.viewmodel;

import java.util.List;
import jp.ojimalab.kebbi.core.Gesture;
import jp.ojimalab.kebbi.core.RuntimePorts.Snapshot;
import jp.ojimalab.kebbi.core.RuntimePorts.State;

/** Immutable screen state. It contains neither connection credentials nor mutable core models. */
public final class ConversationUiState {
  public final State turnState;
  public final boolean connected, ttsDone, motionDone, continuous;
  public final boolean canEditConversation, canStartTurn;
  public final String input, reply, motion, error, backendStatus, mappingStatus, latestLatency;
  public final Gesture gesture;
  public final int languageIndex, replyModelIndex, experimentIndex, sentenceIndex, sentenceCount;
  public final List<String> motionNames;

  ConversationUiState(Snapshot turn, String reply, String error, String backendStatus,
      String mappingStatus, String latestLatency, List<String> motionNames, int languageIndex,
      int replyModelIndex, int experimentIndex) {
    turnState = turn == null ? State.IDLE : turn.state;
    connected = turn != null && turn.connected;
    continuous = turn != null && turn.continuous;
    ttsDone = turn == null || turn.ttsDone;
    motionDone = turn == null || turn.motionDone;
    canEditConversation = turnState == State.IDLE && !continuous;
    canStartTurn = connected && canEditConversation;
    input = turn == null ? "" : turn.text;
    motion = turn == null ? "" : turn.motion;
    gesture = turn == null ? Gesture.none : turn.gesture;
    sentenceIndex = turn == null ? -1 : turn.sentenceIndex;
    sentenceCount = turn == null ? 0 : turn.sentenceCount;
    this.reply = reply;
    this.error = error;
    this.backendStatus = backendStatus;
    this.mappingStatus = mappingStatus;
    this.latestLatency = latestLatency;
    this.motionNames = motionNames;
    this.languageIndex = languageIndex;
    this.replyModelIndex = replyModelIndex;
    this.experimentIndex = experimentIndex;
  }
}
