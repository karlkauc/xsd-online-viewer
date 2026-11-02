+++
title = "Privacy policy"
heading = "Privacy policy"
description = "What data the XSD Viewer processes, why, for how long and who receives it, and what rights you have."
lastmod = 2026-11-02
noindex = true
+++

## Summary

- What you load is processed in memory and is not stored as a file. The exceptions are described below.
- There are no cookies, no client-side analytics and no third-party scripts.
- Your IP address is processed to run the site. Our hosting provider keeps it in request logs for 30 days.
- Usage statistics are kept without your raw IP address. They are pseudonymous, not fully anonymous.

## Who is responsible

Karl Kauc, Vienna, Austria, is the controller under the GDPR.
Email: [karl.kauc@gmail.com](mailto:karl.kauc@gmail.com)

## Schemas and documents you load

Schemas and XML documents you upload, paste or load from a URL are processed in memory. A parsed schema stays in
a memory cache for up to 60 minutes after its last use, so that you can keep working with it. It is not written to
disk. For a URL, our server fetches the address you enter.

Two parts of the statistics described below can contain small pieces of what you load: file names or URLs, and error
messages of failed loads. A third exception concerns generated sample documents and is described under
[Sample diagnostics](#sample-diagnostics).

If you choose to open a schema or document in the XML Viewer, your browser passes it directly to that site.

## Request logs

Every request reaches our hosting provider, which records your IP address, the time, the requested address including
any query string, the response status and your browser's user agent in request logs. These logs are kept for 30 days.

The application itself also uses your IP address briefly in memory for rate limiting, for the visitor hash and for
the country lookup described below. It does not write the IP address to its own logs or database.

The purpose is to operate the site securely and to investigate errors and abuse. The legal basis is our legitimate
interest (Art. 6(1)(f) GDPR).

## Usage statistics

The server records events such as page views, schema loads, validations, exports, shared links, use of certain features and clicks on links to
sister sites. An event can contain:

- a visitor hash: a keyed hash of your IP address and user agent that changes every day, so a visitor is recognised
  within one day but not across days
- your country, looked up in a local copy of the MaxMind GeoLite2 database, so your IP address is not sent to MaxMind
- your user agent and device type
- the page, the referring address without its query string, and any `utm_` campaign parameters in the link
- the file name without its path, or the URL without its query string, of the schema you load
- the target namespace, sizes and counts, duration and outcome
- the error message of a failed load, up to 255 characters, which can quote a short piece of the file

Because the visitor hash and the user agent are stored, these records are treated as personal data. File names and
URLs can contain personal data too. We do not try to identify anyone from them.

The purpose is to understand how the site is used and to improve it. The legal basis is our legitimate interest
(Art. 6(1)(f) GDPR). These records are kept for as long as they are needed for that purpose, including comparisons
over longer periods. There is no fixed deletion date.

## Sample diagnostics

When a generated sample XML fails its own schema check, or the generator had to work around a problem, we store a
diagnostic record so that the generator can be fixed. It contains the generated document (synthetic data, up to 1 MB),
the validator's errors, up to 16 kB of XSD lines around the declarations at fault, the schema's file name or URL and
namespace, your visitor hash, country and device type. Whole schema files are never stored. The purpose and legal basis
are the same as for the usage statistics, and these records are kept for as long as they are needed to fix the fault.

## Feedback

If you send feedback, we store your message, your email address if you give one, the page, the schema name, any error message shown, the visitor hash,
your country, user agent, device type and the app version. Your schema files are not sent.

The purpose is to handle your message and reply if you asked for that. The legal basis is our legitimate interest
in answering and improving the site (Art. 6(1)(f) GDPR). Feedback is kept for as long as it is needed for this
purpose. Giving an email address is optional.

## Stored in your browser

The site uses your browser's local storage to remember your colour theme and whether the structure panel is collapsed. These settings stay on your device and are not
sent to us. You can delete them in your browser at any time.

## Recipients

These providers process data for us:

- **Google Cloud** runs the site and keeps the request logs (Cloud Run, region europe-west1, Belgium). Google may
  process data outside the EU. Such transfers are covered by its data processing terms.
- **Hetzner Online GmbH**, Germany, hosts the statistics database.

We do not sell data or pass it to anyone else, unless the law requires it.

## Your rights

You have the right to access, rectification, erasure, restriction of processing and data portability, and the
right to object to processing based on legitimate interest. To use these rights, email the address above.

The daily visitor hash cannot be traced back to a person, so we may need more information from you, or may be
unable to find your statistics records at all (Art. 11 GDPR).

You can also complain to the Austrian Data Protection Authority (Datenschutzbehörde, Barichgasse 40–42, 1030 Vienna,
[dsb.gv.at](https://www.dsb.gv.at)).

Providing data is neither legally nor contractually required, but the site cannot be reached without your IP address
being processed.

This product includes GeoLite2 data created by MaxMind, available from
[maxmind.com](https://www.maxmind.com).
