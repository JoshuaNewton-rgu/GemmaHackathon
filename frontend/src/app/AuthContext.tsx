import { createContext, useContext, useEffect, useState, type PropsWithChildren } from "react";
import { fetchMe } from "../modules/Auth/auth.api";
import { clearToken, getToken, setToken as persistToken } from "../services/auth";
import type { User } from "../types/api";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  signIn: (token: string, user: User) => Promise<void>;
  signOut: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const token = await getToken();
      if (token) {
        try {
          const { user: me } = await fetchMe();
          setUser(me);
        } catch {
          await clearToken();
        }
      }
      setLoading(false);
    })();
  }, []);

  async function signIn(token: string, newUser: User) {
    await persistToken(token);
    setUser(newUser);
  }

  async function signOut() {
    await clearToken();
    setUser(null);
  }

  async function refreshUser() {
    const { user: me } = await fetchMe();
    setUser(me);
  }

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signOut, refreshUser }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
