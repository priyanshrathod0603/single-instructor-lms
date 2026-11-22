"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { ShieldAlert } from "lucide-react";
import { Modal, ModalContent, ModalHeader, ModalTitle, ModalDescription, ModalFooter } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/hooks/useAuth";

export const DisplacedSessionModal: React.FC = () => {
  const router = useRouter();
  const { isDisplacedSession, displacementReason, dismissDisplacement } = useAuth();
  const [isNavigating, setIsNavigating] = React.useState(false);

  // Guarantee isNavigating is reset whenever isDisplacedSession becomes false
  React.useEffect(() => {
    if (!isDisplacedSession) {
      setIsNavigating(false);
    }
  }, [isDisplacedSession]);

  const handleSignInAgain = async () => {
    if (isNavigating) return;
    setIsNavigating(true);
    try {
      dismissDisplacement();

      // If already on /login, modal dismisses cleanly without navigating
      if (typeof window !== "undefined" && window.location.pathname === "/login") {
        setIsNavigating(false);
        return;
      }

      await router.push("/login");
    } catch (err) {
      console.error("Navigation to /login failed:", err);
    } finally {
      setIsNavigating(false);
    }
  };

  if (!isDisplacedSession) {
    return null;
  }

  return (
    <Modal open={isDisplacedSession}>
      <ModalContent
        hideCloseButton={true}
        onEscapeKeyDown={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
        className="sm:max-w-md border-amber-200"
      >
        <ModalHeader className="items-center text-center">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-amber-100 text-amber-600">
            <ShieldAlert className="h-8 w-8 text-amber-600" />
          </div>
          <ModalTitle className="text-xl font-heading text-slate-900">
            You signed in on another device
          </ModalTitle>
          <ModalDescription className="text-sm text-slate-600 mt-2 leading-relaxed">
            {displacementReason ||
              "Your session on this device has been terminated because your account was logged in on another device. To protect account security, only one active session is permitted at a time."}
          </ModalDescription>
        </ModalHeader>
        <ModalFooter className="mt-4 sm:justify-center">
          <Button
            variant="primary"
            onClick={handleSignInAgain}
            disabled={isNavigating}
            isLoading={isNavigating}
            className="w-full sm:w-auto min-w-[160px]"
          >
            Sign In Again
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
