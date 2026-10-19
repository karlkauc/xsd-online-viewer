+++
title = "Embed an XSD diagram, \"Open in XSD Viewer\" badge and bookmarklet"
heading = "Embed, badge and bookmarklet"
description = "Embed an interactive XML Schema diagram in your documentation with an iframe, add an \"Open in XSD Viewer\" badge to a repository, or open any .xsd link with a bookmarklet."
lastmod = 2026-10-19
cta_label = "Open the viewer"
cta_href = "/"
+++

## Embed the diagram in your documentation

Show an interactive diagram of a public schema on your own site. The iframe loads the schema from its URL and
shows the diagram only, with a link to the full viewer:

```html
<iframe src="https://www.xsd-viewer.online/embed?src=https://example.com/schema.xsd"
        width="100%" height="520" style="border:1px solid #e2e8f0" loading="lazy"
        title="Schema diagram"></iframe>
```

To open the diagram at a particular element, select it in the viewer, copy the part of the address that starts
with `#/id/` and append it to the `src` URL of the iframe.

## Badge for your repository

If your project publishes an XML Schema, let readers browse it as a diagram without cloning anything. Replace the
URL with the raw link to your main `.xsd` (GitHub `blob` links work too; the viewer rewrites them):

```markdown
[![Open in XSD Viewer](https://www.xsd-viewer.online/badge.svg)](https://www.xsd-viewer.online/url?src=https://raw.githubusercontent.com/OWNER/REPO/main/schema.xsd&utm_source=badge)
```

The badge looks like this: ![Open in XSD Viewer](/badge.svg)

Schemas that import or include other files load as long as the referenced files are reachable by relative URL.

## Bookmarklet

Create a bookmark with the following address. On a page that *is* an `.xsd` file (or a GitHub page showing
one), clicking the bookmark opens it in the viewer:

```
javascript:location='https://www.xsd-viewer.online/url?src='+encodeURIComponent(location.href)
```

## Linking to a node

Every node has its own address. Select it in the viewer and use **Share**: the link contains the schema URL and
the node, for example `https://www.xsd-viewer.online/url?src=…#/id/…`.
