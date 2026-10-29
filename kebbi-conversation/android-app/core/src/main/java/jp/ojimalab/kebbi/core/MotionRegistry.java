package jp.ojimalab.kebbi.core;

import com.google.gson.*;
import java.util.*;

public final class MotionRegistry {
  private final EnumMap<Gesture, List<Motion>> map = new EnumMap<>(Gesture.class);
  private final Map<String, Long> played = new HashMap<>();

  public MotionRegistry() {
    for (Gesture g : Gesture.values()) map.put(g, new ArrayList<>());
  }

  public static MotionRegistry parse(String json) {
    MotionRegistry registry = new MotionRegistry();
    JsonObject o = JsonParser.parseString(json).getAsJsonObject();
    Gson gson = new Gson();
    for (Gesture g : Gesture.values())
      if (o.has(g.name()))
        for (JsonElement e : o.getAsJsonArray(g.name())) {
          Motion m =
              e.isJsonPrimitive() ? new Motion(e.getAsString()) : gson.fromJson(e, Motion.class);
          if (m == null || !m.valid())
            throw new IllegalArgumentException("invalid_motion_configuration");
          if (g != Gesture.none) registry.map.get(g).add(m);
        }
    return registry;
  }

  public String json() {
    return new GsonBuilder().setPrettyPrinting().create().toJson(map);
  }

  public List<Motion> entries(Gesture g) {
    return Collections.unmodifiableList(map.get(g));
  }

  public void assign(Gesture g, Motion m) {
    if (g == Gesture.none || !m.valid()) throw new IllegalArgumentException("invalid_mapping");
    map.get(g).removeIf(old -> old.id.equals(m.id));
    map.get(g).add(m);
  }

  public void remove(Gesture g, String id) {
    map.get(g).removeIf(m -> m.id.equals(id));
  }

  public Motion select(Gesture gesture, Set<String> available, long now) {
    if (gesture == Gesture.none) return null;
    for (Motion m : map.get(gesture))
      if (m.enabled && available.contains(m.id) && eligible(m, now)) return m;
    return null;
  }

  public Motion find(String id) {
    for (List<Motion> group : map.values()) for (Motion m : group) if (m.id.equals(id)) return m;
    return new Motion(id);
  }

  public boolean eligible(Motion m, long now) {
    Long last = played.get(m.id);
    return last == null || now - last >= m.cooldownMs;
  }

  public void started(Motion m, long now) {
    played.put(m.id, now);
  }

  public List<SelectionOptions.Candidate> candidates(Set<String> available, long now) {
    Map<String, SelectionOptions.Candidate> result = new LinkedHashMap<>();
    for (Gesture g : Gesture.values()) for (Motion m : map.get(g)) {
      if (m.enabled && available.contains(m.id) && eligible(m, now) && !result.containsKey(m.id)) {
        if (result.size() >= 256) break;
        String description = g.name() + (m.scene.isEmpty() ? "" : ": " + m.scene);
        result.put(m.id, new SelectionOptions.Candidate(m.id, description));
      }
    }
    return new ArrayList<>(result.values());
  }

  public Motion selectId(String id, Set<String> available, long now) {
    if (id == null || !available.contains(id)) return null;
    for (List<Motion> group : map.values()) for (Motion m : group)
      if (m.id.equals(id) && m.enabled && eligible(m, now)) return m;
    return null;
  }

  public List<String> availableGestures(Set<String> available) {
    return availableGestures(available, Long.MAX_VALUE);
  }

  public List<String> availableGestures(Set<String> available, long now) {
    List<String> result = new ArrayList<>();
    for (Gesture g : Gesture.values())
      if (g == Gesture.none || select(g, available, now) != null) result.add(g.name());
    return result;
  }
}
