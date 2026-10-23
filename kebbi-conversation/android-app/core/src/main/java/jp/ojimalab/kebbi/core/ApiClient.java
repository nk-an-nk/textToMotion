package jp.ojimalab.kebbi.core;

import com.google.gson.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.Consumer;

public final class ApiClient implements RuntimePorts.Backend, AutoCloseable {
  private final ExecutorService worker = Executors.newFixedThreadPool(2);
  private final String url, token;
  private volatile boolean closed;

  public ApiClient(String url, String token) {
    URI u = URI.create(url);
    if (!Arrays.asList("http", "https").contains(u.getScheme())
        || u.getHost() == null
        || u.getUserInfo() != null
        || u.getQuery() != null
        || u.getFragment() != null) throw new IllegalArgumentException("invalid_url");
    this.url = url.replaceAll("/+$", "");
    this.token = token;
  }

  private String exchange(
      String path, String method, String body, AtomicReference<HttpURLConnection> active)
      throws IOException {
    HttpURLConnection c = (HttpURLConnection) new URL(url + path).openConnection();
    active.set(c);
    try {
      c.setConnectTimeout(5000);
      c.setReadTimeout(23000);
      c.setRequestMethod(method);
      c.setInstanceFollowRedirects(false);
      c.setRequestProperty("Accept", "application/json");
      if (!token.isEmpty()) c.setRequestProperty("Authorization", "Bearer " + token);
      if (body != null) {
        c.setDoOutput(true);
        c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        try (OutputStream out = c.getOutputStream()) {
          out.write(body.getBytes(StandardCharsets.UTF_8));
        }
      }
      if (c.getResponseCode() != 200) throw new IOException("backend_http_" + c.getResponseCode());
      try (InputStream in = c.getInputStream();
          ByteArrayOutputStream out = new ByteArrayOutputStream()) {
        byte[] buffer = new byte[2048];
        int n;
        while ((n = in.read(buffer)) != -1) {
          if (out.size() + n > 16384) throw new IOException("response_too_large");
          out.write(buffer, 0, n);
        }
        return out.toString("UTF-8");
      }
    } finally {
      active.set(null);
      c.disconnect();
    }
  }

  public RuntimePorts.Cancel respond(
      String session,
      String turn,
      String text,
      String language,
      List<String> gestures,
      Result result) {
    AtomicBoolean canceled = new AtomicBoolean();
    AtomicReference<HttpURLConnection> c = new AtomicReference<>();
    Future<?> future =
        worker.submit(
            () -> {
              try {
                JsonObject body = new JsonObject();
                body.addProperty("session_id", session);
                body.addProperty("conversation_id", turn);
                body.addProperty("text", text);
                body.addProperty("language", language);
                body.add("available_gestures", new Gson().toJsonTree(gestures));
                Reply reply = Reply.parse(exchange("/api/respond", "POST", body.toString(), c));
                if (!closed && !canceled.get()) result.success(reply);
              } catch (Exception error) {
                if (!closed && !canceled.get())
                  result.failure(
                      error instanceof SocketTimeoutException
                          ? "backend_timeout"
                          : error instanceof IOException
                              ? "backend_unavailable"
                              : "invalid_backend_response");
              }
            });
    return () -> {
      canceled.set(true);
      HttpURLConnection active = c.get();
      if (active != null) active.disconnect();
      future.cancel(true);
    };
  }

  public void health(Consumer<String> callback) {
    worker.submit(
        () -> {
          String state;
          try {
            JsonObject o =
                JsonParser.parseString(exchange("/health", "GET", null, new AtomicReference<>()))
                    .getAsJsonObject();
            state =
                "ok".equals(o.get("status").getAsString())
                    ? "接続済み (" + o.get("provider").getAsString() + ")"
                    : "接続エラー";
          } catch (Exception ignored) {
            state = "未接続";
          }
          if (!closed) callback.accept(state);
        });
  }

  public void forget(String session) {
    if (!closed)
      worker.submit(
          () -> {
            try {
              exchange("/api/sessions/" + session, "DELETE", null, new AtomicReference<>());
            } catch (Exception ignored) {
            }
          });
  }

  public void close() {
    closed = true;
    worker.shutdownNow();
  }
}
