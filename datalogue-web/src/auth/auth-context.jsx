import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import {
  getCurrentUser,
  loginAuth,
  logoutAuth,
  refreshAuth,
  setAccessToken,
  setAuthFailureHandler,
  setAuthRefreshHandler,
} from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setAuthRefreshHandler(async () => {
      try {
        const data = await refreshAuth();
        if (!data?.access_token) return false;
        const current = await getCurrentUser();
        setUser(current);
        return true;
      } catch {
        setAccessToken(null);
        setUser(null);
        return false;
      }
    });

    setAuthFailureHandler(() => {
      setAccessToken(null);
      setUser(null);
    });

    const init = async () => {
      try {
        // 页面刷新后 Access Token 会丢失，这里依赖 refresh cookie 做静默恢复。
        await refreshAuth();
        const current = await getCurrentUser();
        setUser(current);
      } catch {
        setAccessToken(null);
        setUser(null);
      } finally {
        setReady(true);
      }
    };

    init();

    return () => {
      setAuthRefreshHandler(null);
      setAuthFailureHandler(null);
    };
  }, []);

  const login = async (username, password) => {
    const tokenData = await loginAuth({ username, password });
    if (!tokenData?.access_token) {
      throw new Error('登录失败：未返回 access_token');
    }
    const current = await getCurrentUser();
    setUser(current);
    return current;
  };

  const logout = async () => {
    try {
      await logoutAuth();
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  };

  const value = useMemo(
    () => ({ user, ready, login, logout }),
    [user, ready],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth 必须在 AuthProvider 内使用');
  }
  return ctx;
}
