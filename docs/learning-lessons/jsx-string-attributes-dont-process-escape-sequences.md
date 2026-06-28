# JSX string attributes do NOT process JavaScript escape sequences

**Date**: 2026-06-27 | **Branch**: `feat/005-spa`

## The Gotcha

In JSX, string attributes enclosed in double quotes (`"..."`) are **JSX string literals**, not JavaScript string literals. They do NOT process escape sequences like `\n`, `\t`, `\\`, etc.

```tsx
// JSX string literal — \n is a literal backslash + n (2 chars)
<NarratorPanel narrative="First paragraph.\n\nSecond paragraph." />

// JavaScript string expression — \n is a newline character (1 char)
<NarratorPanel narrative={"First paragraph.\n\nSecond paragraph."} />

// Template literal — \n is a newline character (1 char)
<NarratorPanel narrative={`First paragraph.\n\nSecond paragraph.`} />
```

## Where This Surfaced

The `NarratorPanel` component splits its narrative on `\n\n+` to produce paragraphs:
```typescript
const paragraphs = narrative.split(/\n\n+/).filter(Boolean)
```

A test was written as:
```tsx
render(<NarratorPanel narrative="First paragraph.\n\nSecond paragraph." />)
expect(screen.getByText('First paragraph.')).toBeInTheDocument() // FAILS
```

The test failed because the narrative string contained the literal 10-character sequence `\n\n`, not two newline characters. The regex `/\n\n+/` found no match, the string was not split, and only one `<p>` element was rendered.

## Fix

In tests: use expression syntax (curly braces) so the value is parsed as a JavaScript string:
```tsx
render(<NarratorPanel narrative={"First paragraph.\n\nSecond paragraph."} />)
```

In production: API responses contain actual newline characters (the backend serializes JSON correctly). The component is correct; only the test was wrong.

## Rule of Thumb

When writing tests that need escape sequences in JSX prop values, always use expression syntax `prop={...}` rather than bare string syntax `prop="..."`.

Cross-references: `tests/unit/components/NarratorPanel.test.tsx`
