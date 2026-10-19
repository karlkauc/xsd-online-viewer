+++
title = "XSD diagram online: XML Schema as an XMLSpy-style diagram"
heading = "XSD diagram online"
description = "Turn an XML Schema into an XMLSpy-style diagram in the browser: sequences, choices, cardinalities, types and documentation. Multi-file schemas from a ZIP, export as PNG or SVG, no install."
lastmod = 2026-10-19
cta_label = "Open the viewer"
cta_href = "/"

[[faq]]
q = "Can I export the diagram?"
a = "Yes, as PNG or SVG from the diagram toolbar, and the whole schema as standalone HTML documentation."

[[faq]]
q = "Does it work with large schemas?"
a = "The viewer is tested with schemas up to about 50 MB. The diagram renders lazily: expand the branches you need, collapse the rest."
+++

Reading an XML Schema as text means keeping a dozen `xs:complexType` and `xs:group` references in your
head. The diagram does that for you, in the notation people know from XMLSpy and Oxygen:

- **Compositors** — `xs:sequence`, `xs:choice` and `xs:all` as their own symbols, so you see at a glance which
  children come in order and which exclude each other.
- **Cardinalities** — `minOccurs`/`maxOccurs` on every element: optional elements dashed, repeating ones stacked.
- **Types and documentation** — the type name, facets and the first line of `xs:documentation` next to each element.
- **Expand and collapse** — open a branch, follow a type reference, collapse it again; pan and zoom with mouse or touch.
- **One selection, three views** — clicking a box selects the node in the tree and the source view jumps to its line.

## Real-world schemas

Industry schemas are rarely one file. Drop a `.zip` with the main schema and its `xs:import`, `xs:include` and
`xs:redefine` targets, or several `.xsd` files at once — the viewer resolves the references and draws the bundle
as one model. Schemas on the web load by URL (`/url?src=https://…`), with GitHub, GitLab and Bitbucket browse
links rewritten to the raw file.

## Export and share

- **PNG or SVG** of the current diagram, for slides and documentation.
- **HTML documentation** of the whole schema — see [XSD documentation generator](/features/documentation).
- **Share links** to a node: the link opens the same schema and selection for a colleague when the schema was
  loaded by URL or from the FundsXML releases.

Try it with a real schema: the [FundsXML releases](/fundsxml) load with one click.
