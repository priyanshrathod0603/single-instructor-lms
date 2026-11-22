import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/Card";

describe("Card Primitive", () => {
  it("renders card with header, title, description, content, and footer", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Course Title</CardTitle>
          <CardDescription>Comprehensive curriculum</CardDescription>
        </CardHeader>
        <CardContent>
          <p>Main body content</p>
        </CardContent>
        <CardFooter>
          <button>Enroll Now</button>
        </CardFooter>
      </Card>
    );

    expect(screen.getByText("Course Title")).toBeInTheDocument();
    expect(screen.getByText("Comprehensive curriculum")).toBeInTheDocument();
    expect(screen.getByText("Main body content")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /enroll now/i })).toBeInTheDocument();
  });
});
