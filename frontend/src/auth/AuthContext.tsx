/**
 * Cognito authentication context.
 * Provides signIn, signUp, signOut, confirmSignUp, getToken.
 *
 * Uses AWS Amplify Auth (lightweight — only the Auth module).
 * Configure Cognito via Amplify.configure in main.tsx.
 */
import React, { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { Amplify } from "aws-amplify";
import {
  signIn as amplifySignIn,
  signUp as amplifySignUp,
  confirmSignUp as amplifyConfirmSignUp,
  signOut as amplifySignOut,
  getCurrentUser,
  fetchAuthSession,
  type SignUpOutput,
} from "aws-amplify/auth";
import { setTokenGetter } from "../api/client";

// ==================== Configure Amplify ====================

const COGNITO_REGION = import.meta.env.VITE_AWS_REGION || "us-east-1";
const COGNITO_USER_POOL_ID = import.meta.env.VITE_COGNITO_USER_POOL_ID || "";
const COGNITO_CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID || "";
const DEV_AUTH = import.meta.env.VITE_DEV_AUTH === "true";
const IS_PLACEHOLDER = COGNITO_CLIENT_ID.includes("xxxxxxxxx") || !COGNITO_CLIENT_ID;

if (!DEV_AUTH && !IS_PLACEHOLDER) {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: COGNITO_USER_POOL_ID,
        userPoolClientId: COGNITO_CLIENT_ID,
      },
    },
  });
}

// ==================== Types ====================

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: { sub: string; email: string } | null;
  error: string | null;
}

interface AuthContextValue extends AuthState {
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, firstName: string, lastName: string) => Promise<SignUpOutput>;
  confirmSignUp: (email: string, code: string) => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// ==================== Provider ====================

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    user: null,
    error: null,
  });

  // --- Token getter for API client ---
  const getToken = useCallback(async (): Promise<string | null> => {
    if (DEV_AUTH || IS_PLACEHOLDER) {
      // Dev mode: return a fake JWT so API calls include Authorization header
      const payload = btoa(JSON.stringify({ sub: "dev-user-001", email: "dev@localhost" }));
      return `dev.${payload}.fake-signature`;
    }
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      return token ?? null;
    } catch {
      return null;
    }
  }, []);

  // Register token getter with API client
  useEffect(() => {
    setTokenGetter(getToken);
  }, [getToken]);

  // Check existing session on mount
  useEffect(() => {
    if (DEV_AUTH || IS_PLACEHOLDER) {
      // Dev mode: auto-login with fake user, skip Cognito
      console.log("[Auth] Dev mode — auto-login (no Cognito needed)");
      setState({
        isAuthenticated: true,
        isLoading: false,
        user: { sub: "dev-user-001", email: "dev@localhost" },
        error: null,
      });
      return;
    }
    checkSession();
  }, []);

  async function checkSession() {
    try {
      const user = await getCurrentUser();
      const token = await getToken();
      if (user && token) {
        const payload = JSON.parse(atob(token.split(".")[1]));
        setState({
          isAuthenticated: true,
          isLoading: false,
          user: { sub: payload.sub, email: payload.email },
          error: null,
        });
      }
    } catch {
      setState((s) => ({ ...s, isLoading: false }));
    }
  }

  // --- Auth actions ---
  async function signIn(email: string, password: string) {
    setState((s) => ({ ...s, error: null }));
    try {
      await amplifySignIn({ username: email, password });
      await checkSession();
    } catch (e: any) {
      const msg = e?.message || "Sign in failed";
      setState((s) => ({ ...s, error: msg }));
      throw e;
    }
  }

  async function signUp(email: string, password: string, firstName: string, lastName: string) {
    setState((s) => ({ ...s, error: null }));
    try {
      const result = await amplifySignUp({
        username: email,
        password,
        options: {
          userAttributes: {
            email,
            given_name: firstName,
            family_name: lastName,
          },
        },
      });
      return result;
    } catch (e: any) {
      const msg = e?.message || "Sign up failed";
      setState((s) => ({ ...s, error: msg }));
      throw e;
    }
  }

  async function confirmSignUp(email: string, code: string) {
    setState((s) => ({ ...s, error: null }));
    try {
      await amplifyConfirmSignUp({ username: email, confirmationCode: code });
    } catch (e: any) {
      const msg = e?.message || "Confirmation failed";
      setState((s) => ({ ...s, error: msg }));
      throw e;
    }
  }

  async function signOut() {
    await amplifySignOut();
    setState({
      isAuthenticated: false,
      isLoading: false,
      user: null,
      error: null,
    });
  }

  function clearError() {
    setState((s) => ({ ...s, error: null }));
  }

  return (
    <AuthContext.Provider
      value={{
        ...state,
        signIn,
        signUp,
        confirmSignUp,
        signOut,
        getToken,
        clearError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ==================== Hook ====================

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
