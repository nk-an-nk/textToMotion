package jp.ojimalab.kebbi.core;

import static jp.ojimalab.kebbi.core.RuntimePorts.*;
import static org.junit.Assert.*;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import org.junit.*;

/** Real HTTP -> FastAPI mock LLM -> controller -> MockRobotAdapter -> IDLE. */
public class HttpFlowTest {
  @Test
  public void actualBackendConversationCompletes() throws Exception {
    for (String[] condition : Arrays.asList(new String[]{"category", "basic"}, new String[]{"category", "expanded"}, new String[]{"direct", "basic"}))
      for (String model : Arrays.asList("", SelectionOptions.REPLY_MODELS.get(0), SelectionOptions.REPLY_MODELS.get(1)))
        complete(condition[0], condition[1], model);
  }

  private void complete(String mode, String profile, String model) throws Exception {
    String url = System.getenv("KEBBI_TEST_BACKEND");
    Assume.assumeTrue("Run scripts/verify.sh for HTTP integration", url != null);
    ScheduledExecutorService ui = Executors.newSingleThreadScheduledExecutor();
    Scheduler scheduler =
        new Scheduler() {
          public long now() {
            return System.nanoTime() / 1000000;
          }

          public void execute(Runnable r) {
            ui.execute(r);
          }

          public Cancel later(long d, Runnable r) {
            ScheduledFuture<?> f = ui.schedule(r, d, TimeUnit.MILLISECONDS);
            return () -> f.cancel(false);
          }
        };
    ApiClient backend = new ApiClient(url, "");
    AtomicReference<ConversationController> app = new AtomicReference<>();
    CountDownLatch done = new CountDownLatch(1);
    List<String> events = Collections.synchronizedList(new ArrayList<>());
    AtomicReference<Snapshot> latest = new AtomicReference<>();
    AtomicReference<Map<String,Object>> metrics = new AtomicReference<>();
    try {
      ui.submit(
              () -> {
                MotionRegistry registry =
                    MotionRegistry.parse("{\"greet\":[{\"id\":\"mock_wave\"}]}");
                ConversationController controller =
                    new ConversationController(
                        new MockRobotAdapter(scheduler),
                        backend,
                        scheduler,
                        (t, n, f) -> { events.add(n); if (n.equals("metrics")) metrics.set(f); },
                        s -> {
                          latest.set(s);
                          if (s.state == State.IDLE && !s.speech.isEmpty()) done.countDown();
                        },
                        registry);
                app.set(controller);
                controller.experiment(mode, profile);
                if (!model.isEmpty()) controller.replyModel(model);
                controller.connect();
                ui.execute(() -> controller.submit("Hello, Kebbi!"));
              })
          .get(5, TimeUnit.SECONDS);
      boolean completed = done.await(12, TimeUnit.SECONDS);
      assertTrue(
          "Flow must finish; state="
              + latest.get().state
              + " error="
              + latest.get().message
              + " events="
              + events,
          completed);
      Snapshot s = latest.get();
      assertEquals(State.IDLE, s.state);
      assertEquals(2, s.sentenceCount);
      assertEquals(2, Collections.frequency(events,"sentence_complete"));
      assertEquals(2, Collections.frequency(events,"tts_request"));
      assertEquals(mode.equals("direct") ? Gesture.none : Gesture.greet, s.gesture);
      assertEquals("Hello! Nice to meet you!", s.speech);
      if (!model.isEmpty()) {
        assertEquals(model, metrics.get().get("reply_model"));
        assertEquals("mock", metrics.get().get("motion_model"));
        assertEquals(0L, metrics.get().get("text_generation_ms"));
        assertEquals(0L, metrics.get().get("motion_selection_ms"));
      }
      assertTrue(s.ttsDone && s.motionDone);
      assertTrue(
          events.containsAll(
              Arrays.asList(
                  "llm_response_received",
                  "tts_request",
                  "motion_request",
                  "tts_complete",
                  "sentence_complete",
                  "metrics")));
    } finally {
      if (app.get() != null) ui.submit(() -> app.get().close()).get(3, TimeUnit.SECONDS);
      backend.close();
      ui.shutdownNow();
    }
  }
}
