package jp.ojimalab.kebbi.core;

import com.google.gson.*;
import java.util.*;

public final class MotionRegistry {
  private final EnumMap<Gesture, List<Motion>> map = new EnumMap<>(Gesture.class);
  private final Map<String, Long> played = new HashMap<>();
  private Map<String, Motion> indexed;

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
    indexed = null;
    if (g == Gesture.none || !m.valid()) throw new IllegalArgumentException("invalid_mapping");
    map.get(g).removeIf(old -> old.id.equals(m.id));
    map.get(g).add(m);
  }

  public void replaceMappings(MotionRegistry other) {
    indexed = null;
    for (Gesture g : Gesture.values()) {
      map.get(g).clear(); map.get(g).addAll(other.map.get(g));
    }
  }

  public void remove(Gesture g, String id) {
    indexed = null;
    map.get(g).removeIf(m -> m.id.equals(id));
  }

  public Motion select(Gesture gesture, Set<String> available, long now) {
    return select(gesture, available, now, false);
  }

  public Motion select(Gesture gesture, Set<String> available, long now, boolean expanded) {
    return selectForSentence(gesture,available,now,expanded,Collections.emptyList());
  }

  public Motion selectForSentence(Gesture gesture, Set<String> available, long now, boolean expanded, Collection<String> playedThisReply) {
    if (gesture == Gesture.none) return null;
    Motion result = null;
    long oldest = Long.MAX_VALUE;
    for (Motion m : map.get(gesture)) {
      if (!m.enabled || (expanded && m.basicOnly) || !available.contains(m.id) || (!eligible(m, now) && !playedThisReply.contains(m.id))) continue;
      long last = played.containsKey(m.id) ? played.get(m.id) : Long.MIN_VALUE;
      if (result == null || last < oldest) { result = m; oldest = last; }
    }
    return result;
  }

  public Motion find(String id) {
    if (indexed == null) {
      indexed = new HashMap<>();
      for (List<Motion> group : map.values()) for (Motion m : group) indexed.putIfAbsent(m.id, m);
    }
    Motion found = indexed.get(id);
    return found == null ? new Motion(id) : found;
  }

  public boolean eligible(Motion m, long now) {
    Long last = played.get(m.id);
    return last == null || now - last >= m.cooldownMs;
  }

  public void started(Motion m, long now) {
    played.put(m.id, now);
  }

  /** Direct selection covers the full SDK catalog, independently of category mappings. */
  public List<SelectionOptions.Candidate> candidates(Set<String> available, long now) {
    List<SelectionOptions.Candidate> result = new ArrayList<>();
    for (String id : new TreeSet<>(available)) {
      Motion m = find(id);
      if (!m.valid() || !eligible(m, now)) continue;
      String words = id.replaceAll("([a-z])([A-Z])", "$1 $2").replace('_', ' ');
      String description = "SDK motion name: " + words;
      if (!m.scene.isEmpty()) description += "; " + m.scene;
      if (description.length() > 300) description = description.substring(0, 300);
      result.add(new SelectionOptions.Candidate(id, description));
    }
    return result;
  }

  public Motion selectId(String id, Set<String> available, long now) {
    if (id == null || !available.contains(id)) return null;
    Motion m = find(id);
    return m.valid() && eligible(m, now) ? m : null;
  }

  public List<String> availableGestures(Set<String> available) {
    return availableGestures(available, Long.MAX_VALUE);
  }

  public List<String> availableGestures(Set<String> available, long now) {
    return availableGestures(available, now, false);
  }

  public List<String> availableGestures(Set<String> available, long now, boolean expanded) {
    List<String> result = new ArrayList<>();
    for (Gesture g : Gesture.values())
      if (g == Gesture.none || select(g, available, now, expanded) != null) result.add(g.name());
    return result;
  }
}
