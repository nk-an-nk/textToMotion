package jp.ojimalab.kebbi.ui.view;

import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

import android.app.Application;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Spinner;
import android.widget.TextView;
import androidx.lifecycle.ViewModelProvider;
import java.time.Duration;
import jp.ojimalab.kebbi.core.SelectionOptions;
import jp.ojimalab.kebbi.ui.viewmodel.ConversationViewModel;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.LooperMode;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 28)
@LooperMode(LooperMode.Mode.PAUSED)
public class ConversationActivityTest {
  private Application app;
  private SharedPreferences prefs;

  @Before
  public void setup() {
    app = RuntimeEnvironment.getApplication();
    prefs = app.getSharedPreferences("kebbi", Context.MODE_PRIVATE);
    prefs.edit().clear().putString("url", "http://127.0.0.1:1").commit();
  }

  @Test
  public void existingLauncherAndStoredSettingsReachTheConversationScreen() throws Exception {
    assertEquals(ConversationActivity.class.getName(), app.getPackageManager().getActivityInfo(
        new ComponentName(app, "jp.ojimalab.kebbi.MainActivity"), 0).targetActivity);
    prefs.edit().putString("language", "ja").putInt("experiment", 1)
        .putString("reply_model", SelectionOptions.REPLY_MODELS.get(2)).commit();
    try (ActivityController<ConversationActivity> lifecycle =
        Robolectric.buildActivity(ConversationActivity.class).setup()) {
      ConversationActivity activity = lifecycle.get();
      ConversationViewModel model = new ViewModelProvider(activity).get(ConversationViewModel.class);
      assertEquals(1, model.screen().getValue().languageIndex);
      assertEquals(1, model.screen().getValue().experimentIndex);
      Spinner modelPicker = activity.findViewById(1010);
      assertEquals(2, modelPicker.getSelectedItemPosition());
      assertTrue(activity.findViewById(1003).isEnabled());
    }
  }

  @Test
  public void mockSpeechAndGestureUpdateTheScreenAndPersistTiming() {
    try (ActivityController<ConversationActivity> lifecycle =
        Robolectric.buildActivity(ConversationActivity.class).setup()) {
      ConversationActivity activity = lifecycle.get();
      EditText input = activity.findViewById(1002);
      input.setText("こんにちは");
      Button play = findButton(activity.findViewById(android.R.id.content), "TTS + ジェスチャー");
      assertNotNull(play);
      play.performClick();
      assertTrue(text(activity, 1007).contains("SPEAKING"));
      assertTrue(text(activity, 1005).contains("こんにちは"));
      assertTrue(text(activity, 1006).contains("mock_wave"));

      shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(2));
      assertTrue(text(activity, 1007).contains("IDLE"));
      assertTrue(text(activity, 1008).contains("completed"));
      assertTrue(new java.io.File(app.getFilesDir(), "latency-history.json").isFile());
    }
  }

  private static String text(ConversationActivity activity, int id) {
    return ((TextView) activity.findViewById(id)).getText().toString();
  }

  private static Button findButton(View root, String label) {
    if (root instanceof Button && label.contentEquals(((Button) root).getText())) return (Button) root;
    if (root instanceof ViewGroup) {
      ViewGroup group = (ViewGroup) root;
      for (int i = 0; i < group.getChildCount(); i++) {
        Button found = findButton(group.getChildAt(i), label);
        if (found != null) return found;
      }
    }
    return null;
  }
}
