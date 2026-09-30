// Minimal code editor: a <textarea> with a line-number gutter, Tab indentation,
// auto-indent on Enter and line highlighting (used when clicking an observation's line number).

export class CodeEditor {
  constructor(container, { onChange } = {}) {
    this.gutter = document.createElement("div");
    this.gutter.className = "gutter";
    this.textarea = document.createElement("textarea");
    this.textarea.spellcheck = false;
    this.textarea.setAttribute("autocapitalize", "off");
    this.textarea.setAttribute("autocomplete", "off");
    this.textarea.placeholder = "def solve(...):\n    ...";
    container.append(this.gutter, this.textarea);
    this.highlighted = null;
    this.onChange = onChange || (() => {});

    this.textarea.addEventListener("input", () => { this.highlighted = null; this.renderGutter(); this.onChange(); });
    this.textarea.addEventListener("scroll", () => { this.gutter.scrollTop = this.textarea.scrollTop; });
    this.textarea.addEventListener("keydown", (e) => this.handleKey(e));
    this.renderGutter();
  }

  get value() { return this.textarea.value; }
  set value(text) { this.textarea.value = text; this.highlighted = null; this.renderGutter(); }

  renderGutter() {
    const lines = this.textarea.value.split("\n").length;
    let html = "";
    for (let i = 1; i <= lines; i++) {
      html += i === this.highlighted ? `<span class="hl">${i}</span>\n` : `${i}\n`;
    }
    this.gutter.innerHTML = html;
    this.gutter.scrollTop = this.textarea.scrollTop;
  }

  highlightLine(line) {
    const lines = this.textarea.value.split("\n");
    if (!line || line > lines.length) return;
    this.highlighted = line;
    this.renderGutter();
    const start = lines.slice(0, line - 1).join("\n").length + (line > 1 ? 1 : 0);
    this.textarea.focus();
    this.textarea.setSelectionRange(start, start + lines[line - 1].length);
    const lineHeight = parseFloat(getComputedStyle(this.textarea).lineHeight) || 20;
    this.textarea.scrollTop = Math.max(0, (line - 4) * lineHeight);
    this.textarea.closest(".editor-card")?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  handleKey(e) {
    const ta = this.textarea;
    if (e.key === "Tab") {
      e.preventDefault();
      const { selectionStart: s, selectionEnd: end, value } = ta;
      if (s === end && !e.shiftKey) {
        ta.setRangeText("    ", s, end, "end");
      } else {
        // indent / unindent every selected line
        const lineStart = value.lastIndexOf("\n", s - 1) + 1;
        const block = value.slice(lineStart, end);
        const changed = e.shiftKey
          ? block.replace(/^ {1,4}/gm, "")
          : block.replace(/^/gm, "    ");
        ta.setRangeText(changed, lineStart, end, "select");
      }
      ta.dispatchEvent(new Event("input"));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const { selectionStart: s, value } = ta;
      const lineStart = value.lastIndexOf("\n", s - 1) + 1;
      const line = value.slice(lineStart, s);
      let indent = line.match(/^\s*/)[0];
      if (/:\s*$/.test(line)) indent += "    ";
      ta.setRangeText("\n" + indent, s, ta.selectionEnd, "end");
      ta.dispatchEvent(new Event("input"));
    }
  }
}
