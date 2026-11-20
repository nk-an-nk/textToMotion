package jp.ojimalab.kebbi.data;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.AtomicFile;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Set;
import jp.ojimalab.kebbi.core.Gesture;
import jp.ojimalab.kebbi.core.Motion;
import jp.ojimalab.kebbi.core.MotionRegistry;

/** Local motion assignments and the last catalog exported by the robot. */
public final class MotionStore {
  private final Context context;
  private final SharedPreferences prefs;
  private final AtomicFile catalog;

  public MotionStore(Context context, SettingsStore settings) {
    this.context = context;
    this.prefs = settings.preferences();
    this.catalog = new AtomicFile(new File(context.getFilesDir(), "motion-catalog.json"));
  }

  public MotionRegistry load() {
    String stored = prefs.getString("mapping", null);
    if (stored != null) return MotionRegistry.parse(stored);
    try (InputStream in = context.getAssets().open("gesture_mapping.json");
        ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      byte[] buffer = new byte[2048];
      int count;
      while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
      return MotionRegistry.parse(out.toString("UTF-8"));
    } catch (IOException ignored) {
      return new MotionRegistry();
    }
  }

  public void save(MotionRegistry registry) {
    prefs.edit().putString("mapping", registry.json()).apply();
  }

  /** Validates the entire server response against the device, then replaces and saves it. */
  public int installServerMapping(String body, Set<String> available, MotionRegistry registry) {
    JsonObject response = JsonParser.parseString(body).getAsJsonObject();
    MotionRegistry replacement = MotionRegistry.parse(response.get("mapping").toString());
    int count = 0;
    for (Gesture gesture : Gesture.values()) {
      for (Motion motion : replacement.entries(gesture)) {
        if (!available.contains(motion.id)) throw new IllegalArgumentException("unknown_motion");
        count++;
      }
    }
    if (count == 0) throw new IllegalArgumentException("empty_mapping");
    int gifCount = response.has("gif_count") ? response.get("gif_count").getAsInt() : 0;
    registry.replaceMappings(replacement);
    save(registry);
    return gifCount;
  }

  public void writeCatalog(List<String> names) {
    FileOutputStream out = null;
    try {
      out = catalog.startWrite();
      out.write(new Gson().toJson(names).getBytes(StandardCharsets.UTF_8));
      catalog.finishWrite(out);
    } catch (IOException ignored) {
      if (out != null) catalog.failWrite(out);
    }
  }
}
