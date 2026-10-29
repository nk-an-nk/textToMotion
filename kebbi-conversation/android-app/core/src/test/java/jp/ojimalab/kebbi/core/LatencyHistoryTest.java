package jp.ojimalab.kebbi.core;
import static org.junit.Assert.*;
import java.util.*;
import org.junit.Test;

public class LatencyHistoryTest {
  @Test public void modelComparisonsKeepSeparateAveragesAndRoundTrip() {
    LatencyHistory h = new LatencyHistory();
    for (int i=0;i<2;i++) {
      Map<String,Object> f=fields("completed","conversation_text",2000+i*1000);
      f.put("reply_model",SelectionOptions.REPLY_MODELS.get(i));
      f.put("motion_model",SelectionOptions.REPLY_MODELS.get(0));
      f.put("text_generation_ms",1000L+i*1000);f.put("motion_selection_ms",900L);
      h.record(UUID.randomUUID().toString(),f,i);
    }
    assertTrue(h.summaryText().contains("文章生成 1.000秒（n=1）"));
    assertTrue(h.summaryText().contains("文章生成 2.000秒（n=1）"));
    assertTrue(h.latestText().contains("gpt-4.1-2025-04-14"));
    assertTrue(h.latestText().contains("動作選択 0.900秒"));
    assertEquals(h.json(),LatencyHistory.parse(h.json()).json());
    assertTrue(h.csv().contains("reply_model,motion_model"));
  }
  private Map<String,Object> fields(String status, String input, long llm) {
    Map<String,Object> f = new LinkedHashMap<>();
    f.put("status",status); f.put("input_mode",input); f.put("selection_mode","direct");
    f.put("gesture_profile","basic"); f.put("llm_ms",llm); return f;
  }

  @Test public void roundTripBoundAndMetadataAllowlist() {
    LatencyHistory h = new LatencyHistory();
    for (int i=0; i<205; i++) {
      Map<String,Object> f = fields("completed","conversation_text",1000+i);
      f.put("speech","private utterance"); f.put("api_key","secret value");
      h.record(new UUID(0,i).toString(),f,i);
    }
    assertEquals(200,h.entries().size());
    assertEquals(5,h.entries().get(0).recordedAt);
    assertFalse(h.json().contains("private utterance"));
    assertFalse(h.json().contains("secret value"));
    assertEquals(h.json(),LatencyHistory.parse(h.json()).json());
  }

  @Test public void failuresAndDiagnosticsAreNotAveragedAsZero() {
    LatencyHistory h = new LatencyHistory();
    h.record(UUID.randomUUID().toString(),fields("completed","conversation_text",1000),0);
    h.record(UUID.randomUUID().toString(),fields("error","conversation_text",9000),1);
    h.record(UUID.randomUUID().toString(),fields("completed","tts_only",7000),2);
    assertTrue(h.summaryText().contains("1.000秒（n=1）"));
    assertTrue(h.historyText().contains("error"));
    assertTrue(h.latestText().contains("返答開始 —"));
  }

  @Test public void duplicateIdReplacesAndCsvEscapesFormulaAndMissingValues() {
    LatencyHistory h = new LatencyHistory(); String id=UUID.randomUUID().toString();
    Map<String,Object> f=fields("completed","conversation_voice",1000);
    f.put("motion_id","=test,\"quoted\""); f.put("asr_ms",Double.NaN);
    f.put("reply_latency_ms",-1); f.put("start_difference_ms",-20);
    h.record(id,f,0); h.record(id,f,10);
    assertEquals(1,h.entries().size());
    assertFalse(h.latest().timings.containsKey("asr_ms"));
    assertFalse(h.latest().timings.containsKey("reply_latency_ms"));
    assertEquals(Long.valueOf(-20),h.latest().timings.get("start_difference_ms"));
    assertTrue(h.csv().contains("'="));
    assertTrue(h.csv().contains("\"\"quoted\"\""));
    h.clear(); assertTrue(h.entries().isEmpty());
  }

  @Test public void languageGroupsAreNotMixed() {
    LatencyHistory h=new LatencyHistory();
    Map<String,Object> en=fields("completed","conversation_text",1000);en.put("language","en");
    Map<String,Object> ja=fields("completed","conversation_text",3000);ja.put("language","ja");
    h.record(UUID.randomUUID().toString(),en,0);h.record(UUID.randomUUID().toString(),ja,1);
    assertTrue(h.summaryText().contains("英語"));assertTrue(h.summaryText().contains("日本語"));
    assertTrue(h.summaryText().contains("1.000秒（n=1）"));assertTrue(h.summaryText().contains("3.000秒（n=1）"));
    assertEquals("ja",LatencyHistory.parse(h.json()).latest().language);
    assertTrue(h.csv().contains("input_mode,language,status"));
  }
}
