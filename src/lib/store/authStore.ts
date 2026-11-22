import { create } from "zustand";
import { User } from "@/types/auth";
import { SESSION_REVOKED_EVENT } from "@/lib/api/errors";

interface AuthState {
  user: User | null;
  isInitialized: boolean;
  isDisplacedSession: boolean;
  displacementReason: string | null;
  setUser: (user: User | null) => void;
  setDisplacedSession: (isDisplaced: boolean, reason?: string | null) => void;
  logout: () => void;
  reset: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isInitialized: false,
  isDisplacedSession: false,
  displacementReason: null,

  setUser: (user) => set({ user, isInitialized: true }),

  setDisplacedSession: (isDisplaced, reason = null) =>
    set({
      isDisplacedSession: isDisplaced,
      displacementReason: isDisplaced
        ? reason || "Your session has been terminated because a newer login occurred on another device."
        : null,
      user: null,
      isInitialized: true,
    }),

  logout: () =>
    set({
      user: null,
      isInitialized: true,
      isDisplacedSession: false,
      displacementReason: null,
    }),

  reset: () =>
    set({
      user: null,
      isInitialized: false,
      isDisplacedSession: false,
      displacementReason: null,
    }),
}));

// Setup global listener for SESSION_REVOKED in client environments
if (typeof window !== "undefined") {
  window.addEventListener(SESSION_REVOKED_EVENT, (event: any) => {
    const currentState = useAuthStore.getState();
    if (!currentState.isDisplacedSession) {
      const reason = event.detail?.message || "Your session has been terminated because a newer login occurred on another device.";
      currentState.setDisplacedSession(true, reason);
    }
  });
}
