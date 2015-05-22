# -*- coding: utf-8 -*-

# Copyright 2010 Dirk Holtwick, holtwick.it
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import cgi
import logging

from tempfile import NamedTemporaryFile, SpooledTemporaryFile

from xhtml2pdf.context import PisaContext
from xhtml2pdf.default import DEFAULT_CSS
from xhtml2pdf.parser import pisaParser
from xhtml2pdf.xhtml2pdf_reportlab import PmlBaseDoc, PmlPageTemplate
from xhtml2pdf.util import PisaTempFile, get_box, PyPDF2

from reportlab.platypus.flowables import Spacer
from reportlab.platypus.frames import Frame

log = logging.getLogger("xhtml2pdf")


def pisa_error_document(dest, c):
    out = PisaTempFile(capacity=c.capacity)
    out.write("<p style='background-color:red;'><strong>%d error(s) occured:</strong><p>" % c.err)
    for mode, line, msg, _ in c.log:
        if mode == "error":
            out.write("<pre>%s in line %d: %s</pre>" % (mode, line, cgi.escape(msg)))

    out.write("<p><strong>%d warning(s) occured:</strong><p>" % c.warn)
    for mode, line, msg, _ in c.log:
        if mode == "warning":
            out.write("<p>%s in line %d: %s</p>" % (mode, line, cgi.escape(msg)))

    return pisa_document(out.getvalue(), dest, raise_exception=False)


def pisa_story(src, path=None, link_callback=None, debug=0, default_css=None, xhtml=False, encoding=None, context=None,
               xml_output=None, **kwargs):
    # Prepare Context
    if not context:
        context = PisaContext(path, debug=debug)
        context.path_callback = link_callback

    # Use a default set of CSS definitions to get an expected output
    if default_css is None:
        default_css = DEFAULT_CSS

    # Parse and fill the story
    pisaParser(src, context, default_css, xhtml, encoding, xml_output)

    # Avoid empty documents
    if not context.story:
        context.story = [Spacer(1, 1)]

    if context.indexing_story:
        context.story.append(context.indexing_story)

    # Remove anchors if they do not exist (because of a bug in Reportlab)
    for frag, anchor in context.anchorFrag:
        if anchor not in context.anchorName:
            frag.link = None
    return context


def pisa_document(src, dest=None, path=None, link_callback=None, debug=0, default_css=None, xhtml=False, encoding=None,
                  xml_output=None, raise_exception=True, capacity=100 * 1024, **kwargs):
    log.debug("pisaDocument options:\n  src = %r\n  dest = %r\n  path = %r\n  link_callback = %r\n  xhtml = %r",
              src, dest, path, link_callback, xhtml)
    # Build story
    context = pisa_story(src, path, link_callback, debug, default_css, xhtml, encoding,
                         context=PisaContext(path, debug=debug, capacity=capacity), xml_output=xml_output)

    # Buffer PDF into memory
    out = NamedTemporaryFile()
    doc = PmlBaseDoc(out,
                     pagesize=context.pageSize,
                     author=context.meta["author"].strip(),
                     subject=context.meta["subject"].strip(),
                     keywords=[x.strip() for x in context.meta["keywords"].strip().split(",") if x],
                     title=context.meta["title"].strip(),
                     showBoundary=0,
                     allowSplitting=1)
    # Prepare templates and their frames
    if "body" in context.templateList:
        body = context.templateList["body"]
        del context.templateList["body"]
    else:
        x, y, w, h = get_box("1cm 1cm -1cm -1cm", context.pageSize)
        body = PmlPageTemplate(id="body",
                               frames=[Frame(x, y, w, h,
                                             id="body",
                                             leftPadding=0,
                                             rightPadding=0,
                                             bottomPadding=0,
                                             topPadding=0)],
                               pagesize=context.pageSize)

    doc.addPageTemplates([body] + list(context.templateList.values()))
    # Use multibuild e.g. if a TOC has to be created
    if context.multiBuild:
        doc.multiBuild(context.story)
    else:
        doc.build(context.story)
    # Add watermarks
    if PyPDF2:
        for bgouter in context.pisaBackgroundList:
            # If we have at least one background, then lets do it
            if bgouter:
                istream = out

                output = PyPDF2.PdfFileWriter()
                input1 = PyPDF2.PdfFileReader(istream)
                ctr = 0
                # TODO: Why do we loop over the same list again?
                # see bgouter at line 137
                for bg in context.pisaBackgroundList:
                    page = input1.getPage(ctr)
                    if bg and not bg.not_found() and bg.mimetype == "application/pdf":
                        bginput = PyPDF2.PdfFileReader(bg.get_file())
                        pagebg = bginput.getPage(0)
                        pagebg.mergePage(page)
                        page = pagebg
                    else:
                        log.warn(context.warning("Background PDF %s doesn't exist.", bg))
                    output.addPage(page)
                    ctr += 1
                out = NamedTemporaryFile()
                output.write(out)
                # data = sout.getvalue()
                # Found a background? So leave loop after first occurence
                break
    else:
        log.warn(context.warning("PyPDF2 not installed!"))
    # Get the resulting PDF and write it to the file object
    # passed from the caller
    context.dest = NamedTemporaryFile()
    if dest is not None:
        context.dest.write(dest.getvalue().encode())
    context.dest.write(out.file.read())  # TODO: context.dest is a tempfile as well...
    return context
