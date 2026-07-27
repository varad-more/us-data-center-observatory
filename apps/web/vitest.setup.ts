import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

/**
 * Testing Library registers its own cleanup automatically, but only when Vitest
 * runs with `globals: true`. This project does not, so without this every render
 * accumulates in the document and the second test to query a given testid finds
 * two of them.
 */
afterEach(cleanup);
