package jp.ojimalab.kebbi.core;

import static jp.ojimalab.kebbi.core.RuntimePorts.State;
import static org.junit.Assert.*;

import java.util.Arrays;
import org.junit.Test;

public class SpeechReplacementTest {
  private final ConversationTest.Clock clock = new ConversationTest.Clock();
  private final ConversationTest.FastRobot robot = new ConversationTest.FastRobot();
  private final ConversationTest.Server backend = new ConversationTest.Server();
  private final MotionRegistry registry = MotionRegistry.parse(
      "{\"greet\":[{\"id\":\"mock_wave\"}]}");

  private static final class Input implements SpeechInput {
    Listener listener;
    String language;
    boolean stopped;
    int closes;

    @Override
    public void listen(long token, String language, Listener listener) {
      this.language = language;
      this.listener = listener;
      stopped = false;
    }

    @Override
    public void stopListening() {
      stopped = true;
    }

    @Override
    public void close() {
      closes++;
    }
  }

  private static final class Output implements SpeechOutput {
    Listener listener;
    String text, language;
    int calls, stops, closes;

    @Override
    public void speak(long token, String text, String language, Listener listener) {
      this.text = text;
      this.language = language;
      this.listener = listener;
      calls++;
    }

    @Override
    public void stopSpeaking() {
      stops++;
    }

    @Override
    public void close() {
      closes++;
    }
  }

  private ConversationController connect(SpeechInput input, SpeechOutput output) {
    ConversationController controller = new ConversationController(
        input, output, robot, backend, clock, (turn, event, fields) -> {}, s -> {}, registry);
    controller.settings("ja", true);
    controller.connect();
    return controller;
  }

  private Reply reply() {
    return new Reply("こんにちは。元気です。", Gesture.greet, "ja", null, Arrays.asList(
        new Reply.Sentence("こんにちは。", Gesture.greet, null),
        new Reply.Sentence("元気です。", Gesture.none, null)));
  }

  @Test
  public void replacingOnlyRecognitionKeepsPairedRobotOutput() {
    Input input = new Input();
    ConversationController controller = connect(input, robot);

    controller.listen(false);
    assertEquals("ja", input.language);
    assertEquals(0, robot.listens);
    input.listener.complete("テスト", null);
    assertTrue(input.stopped);
    assertEquals(State.PROCESSING, controller.state());
    backend.result.success(reply());
    assertEquals(1, robot.play);
    assertEquals(1, robot.speak);
    assertEquals("ja", robot.speakLanguage);

    SpeechInput.Listener firstRequest = input.listener;
    controller.stop();
    controller.listen(false);
    firstRequest.complete("古い認識結果", null);
    assertEquals(State.LISTENING, controller.state());
    controller.close();
    assertTrue(input.stopped);
    assertEquals(1, input.closes);
  }

  @Test
  public void replacingOnlySpeechUsesIndependentOutputForEverySentence() {
    Output output = new Output();
    ConversationController controller = connect(robot, output);

    controller.listen(false);
    assertEquals(1, robot.listens);
    robot.asr(robot.token, "テスト", null);
    backend.result.success(reply());
    assertEquals(1, robot.play);
    assertEquals(0, output.calls);
    robot.e.motionStarted(robot.token, "mock_wave");
    assertEquals(1, output.calls);
    assertEquals("こんにちは。", output.text);
    assertEquals("ja", output.language);

    SpeechOutput.Listener firstSentence = output.listener;
    firstSentence.started();
    firstSentence.completed(null);
    clock.advance(80);
    assertEquals(2, output.calls);
    assertEquals("元気です。", output.text);
    assertEquals(0, robot.speak);
    firstSentence.completed(null);
    assertEquals(State.SPEAKING, controller.state());
    output.listener.started();
    output.listener.completed(null);
    assertEquals(State.IDLE, controller.state());
  }

  @Test
  public void stopCancelsReplacementPlaybackAndLateCompletionCannotFinishNextTurn() {
    Output output = new Output();
    ConversationController controller = connect(robot, output);

    controller.testSpeech("テスト", Gesture.none, false);
    SpeechOutput.Listener old = output.listener;
    controller.stop();
    assertEquals(1, output.stops);
    assertEquals(1, robot.stop);

    controller.testSpeech("もう一度", Gesture.none, false);
    old.started();
    old.completed(null);
    assertEquals(State.SPEAKING, controller.state());
    controller.close();
    assertEquals(2, output.stops);
    assertEquals(1, output.closes);
  }
}
