import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "@/lib/store/authStore";
import { User } from "@/types/auth";

describe("authStore (Zustand)", () => {
  beforeEach(() => {
    useAuthStore.getState().reset();
  });

  const mockUser: User = {
    id: "u-123",
    email: "student@example.com",
    full_name: "Test Student",
    is_verified: true,
    is_active: true,
    roles: ["STUDENT"],
    created_at: new Date().toISOString(),
  };

  it("initializes with default empty state", () => {
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isInitialized).toBe(false);
    expect(state.isDisplacedSession).toBe(false);
  });

  it("updates user state upon successful login via setUser", () => {
    useAuthStore.getState().setUser(mockUser);
    const state = useAuthStore.getState();
    expect(state.user).toEqual(mockUser);
    expect(state.isInitialized).toBe(true);
  });

  it("sets displaced session state when single-active-session displacement occurs", () => {
    useAuthStore.getState().setUser(mockUser);
    useAuthStore.getState().setDisplacedSession(true, "Signed in on mobile device");

    const state = useAuthStore.getState();
    expect(state.isDisplacedSession).toBe(true);
    expect(state.displacementReason).toBe("Signed in on mobile device");
    expect(state.user).toBeNull();
  });

  it("clears user and session data on logout", () => {
    useAuthStore.getState().setUser(mockUser);
    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isDisplacedSession).toBe(false);
  });
});
