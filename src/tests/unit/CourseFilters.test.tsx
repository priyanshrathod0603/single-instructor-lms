import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CourseFilters, CourseFilterValues } from "@/components/courses/CourseFilters";

describe("CourseFilters Component", () => {
  const initialValues: CourseFilterValues = {
    search: "",
    tag: "",
    sortBy: "newest",
  };

  it("renders search input, sort dropdown, and tag chips", () => {
    const onFilterChange = vi.fn();
    render(
      <CourseFilters
        initialValues={initialValues}
        availableTags={["Architecture", "Backend"]}
        totalResults={12}
        onFilterChange={onFilterChange}
      />
    );

    expect(screen.getByPlaceholderText(/search courses by topic/i)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /sort courses/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /all topics/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /architecture/i })).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText(/showing/i)).toBeInTheDocument();
  });

  it("triggers callback when tag is clicked", () => {
    const onFilterChange = vi.fn();
    render(
      <CourseFilters
        initialValues={initialValues}
        availableTags={["Architecture", "Backend"]}
        totalResults={5}
        onFilterChange={onFilterChange}
      />
    );

    const archButton = screen.getByRole("button", { name: /architecture/i });
    fireEvent.click(archButton);

    expect(onFilterChange).toHaveBeenCalledWith({
      search: "",
      tag: "Architecture",
      sortBy: "newest",
    });
  });

  it("triggers callback when sort selection changes", () => {
    const onFilterChange = vi.fn();
    render(
      <CourseFilters
        initialValues={initialValues}
        availableTags={["Architecture"]}
        onFilterChange={onFilterChange}
      />
    );

    const sortSelect = screen.getByRole("combobox", { name: /sort courses/i });
    fireEvent.change(sortSelect, { target: { value: "price_asc" } });

    expect(onFilterChange).toHaveBeenCalledWith({
      search: "",
      tag: "",
      sortBy: "price_asc",
    });
  });
});
