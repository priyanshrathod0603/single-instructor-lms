import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalTitle,
  ModalDescription,
} from "@/components/ui/Modal";

describe("Modal Primitive", () => {
  it("renders modal content when open", () => {
    render(
      <Modal open={true}>
        <ModalContent>
          <ModalHeader>
            <ModalTitle>Test Dialog</ModalTitle>
            <ModalDescription>Description of the dialog</ModalDescription>
          </ModalHeader>
          <p>Dialog body text</p>
        </ModalContent>
      </Modal>
    );

    expect(screen.getByText("Test Dialog")).toBeInTheDocument();
    expect(screen.getByText("Description of the dialog")).toBeInTheDocument();
    expect(screen.getByText("Dialog body text")).toBeInTheDocument();
  });
});
