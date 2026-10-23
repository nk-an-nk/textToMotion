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
                        (t, n, f) -> events.add(n),
                        s -> {
                          latest.set(s);
                          if (s.state == State.IDLE && !s.speech.isEmpty()) done.countDown();
                        },
                        registry);
                app.set(controller);
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
      assertEquals("mock_wave", s.motion);
      assertEquals(Gesture.greet, s.gesture);
      assertEquals("Hello! Nice to meet you!", s.speech);
      assertTrue(s.ttsDone && s.motionDone);
      assertTrue(
          events.containsAll(
              Arrays.asList(
                  "llm_response_received",
                  "tts_request",
                  "motion_request",
                  "tts_complete",
                  "motion_complete",
                  "metrics")));
    } finally {
      if (app.get() != null) ui.submit(() -> app.get().close()).get(3, TimeUnit.SECONDS);
      backend.close();
      ui.shutdownNow();
    }
  }
}
