import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";

const AuthContext = createContext(null);
const LOCAL_TILES_KEY = "pitchlab.tiles";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statDefs, setStatDefs] = useState([]);

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
    api.statDefinitions().then(setStatDefs).catch(() => {});
  }, []);

  const login = useCallback(async (body) => setUser(await api.login(body)), []);
  const signup = useCallback(async (body) => setUser(await api.signup(body)), []);
  const logout = useCallback(async () => {
    await api.logout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, setUser, loading, login, signup, logout, statDefs }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

function readLocalTiles() {
  try {
    const saved = JSON.parse(localStorage.getItem(LOCAL_TILES_KEY));
    return Array.isArray(saved) ? saved : null;
  } catch {
    return null;
  }
}

/**
 * Which stats the viewer wants to see, in registry order. Saved to the account when signed in,
 * to this browser otherwise. Returns [keys, setKeys]; keys falls back to the registry defaults.
 */
export function useTilePrefs() {
  const { user, setUser, statDefs } = useAuth();
  const [localKeys, setLocalKeys] = useState(readLocalTiles);

  const saved = user ? user.preferences?.tiles ?? null : localKeys;
  const keys = saved ?? statDefs.filter((d) => d.default).map((d) => d.key);

  const setKeys = useCallback(
    async (next) => {
      if (user) {
        setUser({ ...user, preferences: { ...user.preferences, tiles: next } }); // optimistic
        setUser(await api.setPreferences({ tiles: next }));
      } else {
        setLocalKeys(next);
        try {
          if (next) localStorage.setItem(LOCAL_TILES_KEY, JSON.stringify(next));
          else localStorage.removeItem(LOCAL_TILES_KEY);
        } catch {
          /* storage unavailable (private mode): the choice just won't persist */
        }
      }
    },
    [user, setUser]
  );

  return [keys, setKeys];
}
