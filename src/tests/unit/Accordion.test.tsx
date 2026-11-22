import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/Accordion";

describe("Accordion Component", () => {
  it("renders accordion trigger and toggles content on click", async () => {
    render(
      <Accordion type="single" collapsible>
        <AccordionItem value="item-1">
          <AccordionTrigger>Section 1: Architecture</AccordionTrigger>
          <AccordionContent>Lesson details and breakdown</AccordionContent>
        </AccordionItem>
      </Accordion>
    );

    const trigger = screen.getByRole("button", {
      name: /section 1: architecture/i,
    });
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveAttribute("data-state", "closed");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("data-state", "open");
    expect(screen.getByText("Lesson details and breakdown")).toBeInTheDocument();
  });
});
