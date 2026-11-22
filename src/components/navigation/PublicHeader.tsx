"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Menu,
  X,
  Search,
  GraduationCap,
  ChevronDown,
  BookOpen,
  Layers,
  Shield,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/Sheet";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/Accordion";
import { useAuth } from "@/lib/hooks/useAuth";

export const PublicHeader: React.FC = () => {
  const pathname = usePathname();
  const router = useRouter();
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const { isAuthenticated } = useAuth();

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.push(`/courses?search=${encodeURIComponent(searchQuery.trim())}`);
      setIsMobileOpen(false);
    }
  };

  return (
    <header className="sticky top-0 z-40 w-full border-b border-soft-peach/80 bg-white/95 backdrop-blur-md shadow-subtle">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8 gap-4">
        {/* Brand Logo */}
        <Link href="/" className="flex items-center gap-2.5 group shrink-0">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-teal text-white shadow-sm transition-transform duration-200 group-hover:scale-105">
            <GraduationCap className="h-6 w-6" />
          </div>
          <span className="font-heading text-xl font-extrabold tracking-tight text-slate-900">
            Instructor<span className="text-primary-teal">LMS</span>
          </span>
        </Link>

        {/* Desktop Primary Navigation */}
        <nav className="hidden lg:flex items-center gap-1 xl:gap-2" aria-label="Main Navigation">
          {/* Home */}
          <Link
            href="/"
            className={`rounded-lg px-3 py-2 font-sans text-sm font-semibold transition-colors ${
              pathname === "/"
                ? "bg-accent-mint/50 text-primary-teal font-bold"
                : "text-slate-800 hover:bg-accent-mint/30 hover:text-primary-teal"
            }`}
          >
            Home
          </Link>

          {/* Courses Catalog */}
          <Link
            href="/courses"
            className={`rounded-lg px-3 py-2 font-sans text-sm font-semibold transition-colors ${
              pathname.startsWith("/courses")
                ? "bg-accent-mint/50 text-primary-teal font-bold"
                : "text-slate-800 hover:bg-accent-mint/30 hover:text-primary-teal"
            }`}
          >
            Courses
          </Link>

          {/* Start Learning Mega-Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="group inline-flex items-center gap-1 rounded-lg px-3 py-2 font-sans text-sm font-semibold text-slate-800 hover:bg-accent-mint/30 hover:text-primary-teal focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-teal"
              >
                <span>Start Learning</span>
                <ChevronDown className="h-4 w-4 text-slate-500 transition-transform duration-200 group-data-[state=open]:rotate-180" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-[420px] p-4 shadow-elevated" align="start">
              {/* Brand Header */}
              <div className="mb-3 rounded-xl bg-gradient-to-br from-primary-teal/10 via-accent-mint/20 to-warm-cream p-3.5 border border-soft-peach/60">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-primary-teal" />
                  <span className="font-heading text-xs font-bold uppercase tracking-wider text-primary-teal">
                    Single-Instructor Masterclasses
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-600 font-sans leading-relaxed">
                  Rigorous, end-to-end courses designed and evaluated by the lead architect.
                </p>
              </div>

              <div className="space-y-1">
                <DropdownMenuItem asChild>
                  <Link
                    href="/courses"
                    className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-accent-mint/40 cursor-pointer"
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-teal/10 text-primary-teal">
                      <BookOpen className="h-4 w-4" />
                    </div>
                    <div>
                      <span className="font-heading text-sm font-bold text-slate-900 block">
                        Browse All Curriculum
                      </span>
                      <span className="text-xs text-slate-500 font-sans">
                        Full catalog of active published courses
                      </span>
                    </div>
                  </Link>
                </DropdownMenuItem>

                <DropdownMenuItem asChild>
                  <Link
                    href="/courses?tag=Architecture"
                    className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-accent-mint/40 cursor-pointer"
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-peach/60 text-accent-coral">
                      <Layers className="h-4 w-4" />
                    </div>
                    <div>
                      <span className="font-heading text-sm font-bold text-slate-900 block">
                        System Architecture Track
                      </span>
                      <span className="text-xs text-slate-500 font-sans">
                        Distributed backends, high scale, fault tolerance
                      </span>
                    </div>
                  </Link>
                </DropdownMenuItem>

                <DropdownMenuItem asChild>
                  <Link
                    href="/courses?tag=Security"
                    className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-accent-mint/40 cursor-pointer"
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
                      <Shield className="h-4 w-4" />
                    </div>
                    <div>
                      <span className="font-heading text-sm font-bold text-slate-900 block">
                        Enterprise API Security
                      </span>
                      <span className="text-xs text-slate-500 font-sans">
                        Zero-trust architectures, OWASP mitigation, JWT
                      </span>
                    </div>
                  </Link>
                </DropdownMenuItem>
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Tutorials Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="group inline-flex items-center gap-1 rounded-lg px-3 py-2 font-sans text-sm font-semibold text-slate-800 hover:bg-accent-mint/30 hover:text-primary-teal focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-teal"
              >
                <span>Tutorials</span>
                <ChevronDown className="h-4 w-4 text-slate-500 transition-transform duration-200 group-data-[state=open]:rotate-180" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-[300px] p-2" align="start">
              <DropdownMenuLabel>Curriculum Topics</DropdownMenuLabel>
              <DropdownMenuItem asChild>
                <Link href="/courses?tag=Backend" className="cursor-pointer">
                  Backend Engineering
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/courses?tag=Architecture" className="cursor-pointer">
                  Distributed Systems
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/courses?tag=Security" className="cursor-pointer">
                  Authentication & Security
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <div className="p-2 text-[11px] text-slate-400 font-sans italic">
                Standalone tutorial guides are currently in development.
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Blog (Pending Owner Approval / Coming Soon) */}
          <div className="relative group inline-flex items-center">
            <span
              className="inline-flex items-center gap-1.5 px-3 py-2 font-sans text-sm font-medium text-slate-400 cursor-not-allowed select-none"
              title="Blog articles are scheduled for future release (Pending Owner Approval)"
            >
              Blog
              <Badge variant="outline" size="sm" className="text-[10px] py-0 px-1 border-slate-300 text-slate-400">
                Soon
              </Badge>
            </span>
          </div>

          {/* Notes (Pending Owner Approval / Coming Soon) */}
          <div className="relative group inline-flex items-center">
            <span
              className="inline-flex items-center gap-1.5 px-3 py-2 font-sans text-sm font-medium text-slate-400 cursor-not-allowed select-none"
              title="Course notes are scheduled for future release (Pending Owner Approval)"
            >
              Notes
              <Badge variant="outline" size="sm" className="text-[10px] py-0 px-1 border-slate-300 text-slate-400">
                Soon
              </Badge>
            </span>
          </div>

          {/* Contact Anchor */}
          <Link
            href="/#about"
            className="rounded-lg px-3 py-2 font-sans text-sm font-semibold text-slate-800 hover:bg-accent-mint/30 hover:text-primary-teal transition-colors"
          >
            Contact
          </Link>
        </nav>

        {/* Header Search Bar (Desktop) */}
        <form
          onSubmit={handleSearchSubmit}
          className="relative hidden md:flex items-center flex-1 max-w-xs xl:max-w-sm"
        >
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
            <Search className="h-4 w-4" />
          </div>
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search masterclasses..."
            aria-label="Search courses"
            className="w-full h-10 pl-9 pr-4 rounded-lg border border-soft-peach bg-warm-cream/30 font-sans text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:border-primary-teal focus:outline-none focus:ring-2 focus:ring-primary-teal/20 transition-all"
          />
        </form>

        {/* Desktop Auth CTAs */}
        <div className="hidden md:flex items-center gap-3 shrink-0">
          {isAuthenticated ? (
            <Link href="/app">
              <Button variant="primary" size="sm">
                Go to Dashboard
              </Button>
            </Link>
          ) : (
            <>
              <Link href="/login">
                <Button variant="ghost" size="sm" className="font-semibold text-slate-700">
                  Sign In
                </Button>
              </Link>
              <Link href="/signup">
                <Button variant="primary" size="sm">
                  Get Started
                </Button>
              </Link>
            </>
          )}
        </div>

        {/* Mobile Hamburger Drawer Trigger */}
        <div className="flex lg:hidden">
          <Sheet open={isMobileOpen} onOpenChange={setIsMobileOpen}>
            <SheetTrigger asChild>
              <button
                type="button"
                className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-slate-700 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-teal"
                aria-label="Open mobile navigation menu"
              >
                <Menu className="h-6 w-6" />
              </button>
            </SheetTrigger>
            <SheetContent side="right" className="w-[320px] sm:w-[380px] p-6 flex flex-col justify-between overflow-y-auto">
              <div className="space-y-6">
                <SheetHeader>
                  <SheetTitle className="flex items-center gap-2.5 text-left">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-teal text-white">
                      <GraduationCap className="h-5 w-5" />
                    </div>
                    <span className="font-heading text-lg font-bold text-slate-900">
                      Instructor<span className="text-primary-teal">LMS</span>
                    </span>
                  </SheetTitle>
                </SheetHeader>

                {/* Mobile Search */}
                <form onSubmit={handleSearchSubmit} className="relative">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                  <input
                    type="search"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search courses..."
                    aria-label="Search courses mobile"
                    className="w-full h-11 pl-9 pr-3 rounded-lg border border-soft-peach font-sans text-sm focus:border-primary-teal focus:outline-none"
                  />
                </form>

                {/* Mobile Navigation Links & Accordions */}
                <nav className="flex flex-col space-y-1">
                  <Link
                    href="/"
                    onClick={() => setIsMobileOpen(false)}
                    className="flex h-11 items-center rounded-lg px-3 font-sans text-base font-semibold text-slate-800 hover:bg-accent-mint/40 hover:text-primary-teal transition-colors"
                  >
                    Home
                  </Link>

                  <Link
                    href="/courses"
                    onClick={() => setIsMobileOpen(false)}
                    className="flex h-11 items-center rounded-lg px-3 font-sans text-base font-semibold text-slate-800 hover:bg-accent-mint/40 hover:text-primary-teal transition-colors"
                  >
                    Courses Catalog
                  </Link>

                  <Accordion type="single" collapsible className="w-full">
                    <AccordionItem value="start-learning" className="border-none">
                      <AccordionTrigger className="h-11 px-3 py-0 font-sans text-base font-semibold text-slate-800 hover:no-underline">
                        Start Learning
                      </AccordionTrigger>
                      <AccordionContent className="pl-6 space-y-2 pt-2">
                        <Link
                          href="/courses"
                          onClick={() => setIsMobileOpen(false)}
                          className="block py-1.5 text-sm text-slate-600 hover:text-primary-teal"
                        >
                          All Masterclasses
                        </Link>
                        <Link
                          href="/courses?tag=Architecture"
                          onClick={() => setIsMobileOpen(false)}
                          className="block py-1.5 text-sm text-slate-600 hover:text-primary-teal"
                        >
                          System Architecture Track
                        </Link>
                        <Link
                          href="/courses?tag=Security"
                          onClick={() => setIsMobileOpen(false)}
                          className="block py-1.5 text-sm text-slate-600 hover:text-primary-teal"
                        >
                          Enterprise API Security
                        </Link>
                      </AccordionContent>
                    </AccordionItem>

                    <AccordionItem value="tutorials" className="border-none">
                      <AccordionTrigger className="h-11 px-3 py-0 font-sans text-base font-semibold text-slate-800 hover:no-underline">
                        Tutorials
                      </AccordionTrigger>
                      <AccordionContent className="pl-6 space-y-2 pt-2">
                        <Link
                          href="/courses?tag=Backend"
                          onClick={() => setIsMobileOpen(false)}
                          className="block py-1.5 text-sm text-slate-600 hover:text-primary-teal"
                        >
                          Backend Engineering
                        </Link>
                        <Link
                          href="/courses?tag=Architecture"
                          onClick={() => setIsMobileOpen(false)}
                          className="block py-1.5 text-sm text-slate-600 hover:text-primary-teal"
                        >
                          Distributed Computing
                        </Link>
                      </AccordionContent>
                    </AccordionItem>
                  </Accordion>

                  <div className="flex h-11 items-center justify-between px-3 font-sans text-base text-slate-400">
                    <span>Blog</span>
                    <Badge variant="outline" size="sm" className="text-[10px]">
                      Coming Soon
                    </Badge>
                  </div>

                  <div className="flex h-11 items-center justify-between px-3 font-sans text-base text-slate-400">
                    <span>Notes</span>
                    <Badge variant="outline" size="sm" className="text-[10px]">
                      Coming Soon
                    </Badge>
                  </div>

                  <Link
                    href="/#about"
                    onClick={() => setIsMobileOpen(false)}
                    className="flex h-11 items-center rounded-lg px-3 font-sans text-base font-semibold text-slate-800 hover:bg-accent-mint/40 hover:text-primary-teal transition-colors"
                  >
                    Contact & About
                  </Link>
                </nav>
              </div>

              {/* Mobile Auth CTAs */}
              <div className="pt-6 border-t border-soft-peach flex flex-col gap-3">
                {isAuthenticated ? (
                  <Link href="/app" onClick={() => setIsMobileOpen(false)}>
                    <Button variant="primary" className="w-full">
                      Go to Dashboard
                    </Button>
                  </Link>
                ) : (
                  <>
                    <Link href="/login" onClick={() => setIsMobileOpen(false)}>
                      <Button variant="outline" className="w-full">
                        Sign In
                      </Button>
                    </Link>
                    <Link href="/signup" onClick={() => setIsMobileOpen(false)}>
                      <Button variant="primary" className="w-full">
                        Get Started
                      </Button>
                    </Link>
                  </>
                )}
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
};
