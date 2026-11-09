/**
 * One-click fixes for pasted schemas that fail only for a missing or wrong
 * namespace declaration — a fifth of pasted text failed to load in the usage
 * stats, most often a snippet whose `xs:`/`xsd:` prefix was never declared or
 * a `<schema>` root without the XML Schema namespace. The backend message says
 * what is wrong (`backend/app/parser/errors.py`); this applies that advice.
 */

export const XSD_NS = "http://www.w3.org/2001/XMLSchema";

export interface SchemaRepair {
  text: string;
  /** Button label: what the fix does. */
  label: string;
}

const NAME = "[A-Za-z_][\\w.-]*";
// Skip the prolog (comments, PIs, DOCTYPE) to find the root's start tag.
const ROOT_SCAN = new RegExp(
  `<!--[\\s\\S]*?-->|<\\?[\\s\\S]*?\\?>|<!DOCTYPE[^>]*>|<(${NAME}(?::${NAME})?)`,
  "g",
);
const XML_DECL = /^﻿?\s*<\?xml[\s\S]*?\?>\s*/;

interface Root {
  name: string;
  /** Index just after the element name, where attributes can be inserted. */
  nameEnd: number;
  /** Index of the start tag's closing `>` (or `/>`). */
  tagEnd: number;
}

function findRoot(text: string): Root | null {
  ROOT_SCAN.lastIndex = 0;
  for (let m = ROOT_SCAN.exec(text); m; m = ROOT_SCAN.exec(text)) {
    if (!m[1]) continue;
    const nameEnd = m.index + 1 + m[1].length;
    const tagEnd = text.indexOf(">", nameEnd);
    if (tagEnd < 0) return null;
    return { name: m[1], nameEnd, tagEnd };
  }
  return null;
}

function localName(name: string): string {
  return name.slice(name.indexOf(":") + 1);
}

function insertOnRoot(text: string, root: Root, attribute: string): string {
  return `${text.slice(0, root.nameEnd)} ${attribute}${text.slice(root.nameEnd)}`;
}

function wrap(text: string, prefix: string): string {
  const decl = XML_DECL.exec(text)?.[0] ?? "";
  const body = text.slice(decl.length).trim();
  return `${decl}<${prefix}:schema xmlns:${prefix}="${XSD_NS}">\n${body}\n</${prefix}:schema>\n`;
}

const UNDECLARED = /Namespace prefix (\S+) (?:on|for) \S+ is not defined/;
const NO_NAMESPACE = /the root element <schema> declares no namespace/;
const WRONG_NAMESPACE = /the root element <schema> (?:is in namespace (\S+),|uses .*? namespace \((\S+)\))/;
const FRAGMENT = /a part of an XML Schema rather than a whole one/;

export function repairSchemaText(text: string, message: string): SchemaRepair | null {
  const root = findRoot(text);
  if (!root) return null;

  const undeclared = UNDECLARED.exec(message);
  if (undeclared) {
    const prefix = undeclared[1];
    if (prefix !== "xs" && prefix !== "xsd") return null;
    if (localName(root.name) === "schema") {
      return {
        text: insertOnRoot(text, root, `xmlns:${prefix}="${XSD_NS}"`),
        label: `Declare xmlns:${prefix} and load again`,
      };
    }
    return { text: wrap(text, prefix), label: `Wrap in <${prefix}:schema> and load again` };
  }

  if (NO_NAMESPACE.test(message) && root.name === "schema") {
    return { text: insertOnRoot(text, root, `xmlns="${XSD_NS}"`), label: "Add the XML Schema namespace and load again" };
  }

  const wrong = WRONG_NAMESPACE.exec(message);
  if (wrong && localName(root.name) === "schema") {
    const namespace = (wrong[1] ?? wrong[2]).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const startTag = text.slice(root.nameEnd, root.tagEnd);
    const declaration = new RegExp(`(xmlns(?::${NAME})?\\s*=\\s*["'])${namespace}(["'])`, "g");
    const fixed = startTag.replace(declaration, `$1${XSD_NS}$2`);
    if (fixed === startTag) return null;
    return {
      text: text.slice(0, root.nameEnd) + fixed + text.slice(root.tagEnd),
      label: "Use the XML Schema namespace and load again",
    };
  }

  if (FRAGMENT.test(message)) {
    return { text: wrap(text, "xs"), label: "Wrap in <xs:schema> and load again" };
  }
  return null;
}
