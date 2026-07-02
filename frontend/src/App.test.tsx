import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App toolbar", () => {
  it("renders CSV catalog picker triggers for context fields", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html.match(/catalog-picker-trigger/g)?.length).toBe(3);
    expect(html).toContain('data-picker-kind="inventory"');
    expect(html).toContain('data-picker-kind="equipment"');
    expect(html).toContain('data-picker-kind="recipe"');
  });
  it("renders the clear-all action as a compact two-line button", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain('aria-label="전체 비우기"');
    expect(html).toContain('class="secondary-action clear-all-action"');
    expect(html.match(/clear-all-action-line/g)?.length).toBe(2);
  });
});