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

import copy
import logging
import os
import re
import reportlab

from six import text_type

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.fonts import addMapping
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.frames import Frame, ShowBoundaryValue
from reportlab.platypus.paraparser import ParaFrag, ps2tt, tt2ps

import xhtml2pdf.default
import xhtml2pdf.parser

from xhtml2pdf.w3c import css
from xhtml2pdf.util import (get_size, get_coordinates, get_file, PisaFileObject, get_frame_dimensions, get_color)
from xhtml2pdf.xhtml2pdf_reportlab import (PmlPageTemplate, PmlTableOfContents, PmlParagraph, PmlParagraphAndImage,
                                           PmlPageCount)

try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse

reportlab.rl_config.warnOnMissingFontGlyphs = 0

log = logging.getLogger("xhtml2pdf")

sizeDelta = 2       # amount to reduce font size by for super and sub script
subFraction = 0.4   # fraction of font size that a sub script should be lowered
superFraction = 0.4

NBSP = u"\u00a0"
ListType = (list, tuple)


def clone(self, **kwargs):
    n = ParaFrag(**self.__dict__)
    if kwargs:
        d = n.__dict__
        d.update(kwargs)
        # This else could cause trouble in Paragraphs with images etc.
        if "cbDefn" in d:
            del d["cbDefn"]
    n.bulletText = None
    return n


ParaFrag.clone = clone


def get_paragraph_fragment(style):
    frag = ParaFrag()
    frag.sub = 0
    frag.super = 0
    frag.rise = 0
    frag.underline = 0  # XXX Need to be able to set color to fit CSS tests
    frag.strike = 0
    frag.greek = 0
    frag.link = None
    frag.text = ""
    frag.fontName = "Times-Roman"
    frag.fontName, frag.bold, frag.italic = ps2tt(style.fontName)
    frag.fontSize = style.fontSize
    frag.textColor = style.textColor

    # Extras
    frag.leading = 0
    frag.letterSpacing = "normal"
    frag.leadingSource = "150%"
    frag.leadingSpace = 0
    frag.backColor = None
    frag.spaceBefore = 0
    frag.spaceAfter = 0
    frag.leftIndent = 0
    frag.rightIndent = 0
    frag.firstLineIndent = 0
    frag.keepWithNext = False
    frag.alignment = TA_LEFT
    frag.vAlign = None

    frag.borderWidth = 1
    frag.borderStyle = None
    frag.borderPadding = 0
    frag.borderColor = None

    frag.borderLeftWidth = frag.borderWidth
    frag.borderLeftColor = frag.borderColor
    frag.borderLeftStyle = frag.borderStyle
    frag.borderRightWidth = frag.borderWidth
    frag.borderRightColor = frag.borderColor
    frag.borderRightStyle = frag.borderStyle
    frag.borderTopWidth = frag.borderWidth
    frag.borderTopColor = frag.borderColor
    frag.borderTopStyle = frag.borderStyle
    frag.borderBottomWidth = frag.borderWidth
    frag.borderBottomColor = frag.borderColor
    frag.borderBottomStyle = frag.borderStyle

    frag.paddingLeft = 0
    frag.paddingRight = 0
    frag.paddingTop = 0
    frag.paddingBottom = 0

    frag.listStyleType = None
    frag.listStyleImage = None
    frag.whiteSpace = "normal"

    frag.wordWrap = None

    frag.pageNumber = False
    frag.pageCount = False
    frag.height = None
    frag.width = None

    frag.bulletIndent = 0
    frag.bulletText = None
    frag.bulletFontName = "Helvetica"

    frag.zoom = 1.0

    frag.outline = False
    frag.outlineLevel = 0
    frag.outlineOpen = False

    frag.insideStaticFrame = 0

    return frag


def get_dir_name(path):
    parts = urlparse.urlparse(path)
    if parts.scheme:
        return path
    else:
        return os.path.dirname(os.path.abspath(path))


class PisaCSSBuilder(css.CSSBuilder):
    def at_font_face(self, declarations):
        """
        Embed fonts
        """
        result = self.ruleset([self.selector('*')], declarations)
        data = result[0].values()[0]
        if "src" not in data:
            # invalid - source is required, ignore this specification
            return {}, {}
        names = data["font-family"]

        # Font weight
        fweight = str(data.get("font-weight", "normal")).lower()
        bold = fweight in ("bold", "bolder", "500", "600", "700", "800", "900")
        if not bold and fweight != "normal":
            log.warn(self.c.warning("@fontface, unknown value font-weight '%s'", fweight))

        # Font style
        italic = str(data.get("font-style", "")).lower() in ("italic", "oblique")

        src = self.c.get_file(data["src"], relative=self.c.cssParser.rootPath)
        self.c.load_font(
            names,
            src,
            bold=bold,
            italic=italic)
        return {}, {}

    def _pisa_add_frame(self, name, data, first=False, border=None, size=(0, 0)):
        c = self.c
        if not name:
            name = "-pdf-frame-%d" % c.uid()
        if data.get('is_landscape', False):
            size = (size[1], size[0])
        x, y, w, h = get_frame_dimensions(data, size[0], size[1])
        # print name, x, y, w, h
        #if not (w and h):
        #    return None
        if first:
            return name, None, data.get("-pdf-frame-border", border), x, y, w, h, data

        return (name, data.get("-pdf-frame-content", None),
                data.get("-pdf-frame-border", border), x, y, w, h, data)

    def _get_from_data(self, data, attr, default=None, func=None):
        if not func:
            func = lambda x: x

        if type(attr) in (list, tuple):
            for a in attr:
                if a in data:
                    return func(data[a])
                return default
        else:
            if attr in data:
                return func(data[attr])
            return default

    def at_page(self, name, pseudopage, declarations):
        c = self.c
        data = {}
        name = name or "body"
        page_border = None

        if declarations:
            result = self.ruleset([self.selector('*')], declarations)

            if declarations:
                try:
                    data = result[0].values()[0]
                except Exception:
                    data = result[0].popitem()[1]
                page_border = data.get("-pdf-frame-border", None)

        if name in c.templateList:
            log.warn(self.c.warning("template '%s' has already been defined", name))

        if "-pdf-page-size" in data:
            c.pageSize = xhtml2pdf.default.PML_PAGESIZES.get(str(data["-pdf-page-size"]).lower(), c.pageSize)

        is_landscape = False
        if "size" in data:
            size = data["size"]
            if type(size) is not ListType:
                size = [size]
            size_list = []
            for value in size:
                valueStr = str(value).lower()
                if isinstance(value, tuple):
                    size_list.append(get_size(value))
                elif valueStr == "landscape":
                    is_landscape = True
                elif valueStr == "portrait":
                    is_landscape = False
                elif valueStr in xhtml2pdf.default.PML_PAGESIZES:
                    c.pageSize = xhtml2pdf.default.PML_PAGESIZES[valueStr]
                else:
                    log.warn(c.warning("Unknown size value for @page"))

            if len(size_list) == 2:
                c.pageSize = tuple(size_list)
            if is_landscape:
                c.pageSize = landscape(c.pageSize)

        padding_top = self._get_from_data(data, 'padding-top', 0, get_size)
        padding_left = self._get_from_data(data, 'padding-left', 0, get_size)
        padding_right = self._get_from_data(data, 'padding-right', 0, get_size)
        padding_bottom = self._get_from_data(data, 'padding-bottom', 0, get_size)
        border_color = self._get_from_data(data, ('border-top-color', 'border-bottom-color', 'border-left-color',
                                                  'border-right-color'), None, get_color)
        border_width = self._get_from_data(data, ('border-top-width', 'border-bottom-width', 'border-left-width',
                                                  'border-right-width'), 0, get_size)

        for prop in ("margin-top", "margin-left", "margin-right", "margin-bottom",
                     "top", "left", "right", "bottom", "width", "height"):
            if prop in data:
                c.frameList.append(self._pisa_add_frame(name, data, first=True, border=page_border, size=c.pageSize))
                break

        # Frames have to be calculated after we know the pagesize
        frame_list = []
        static_list = []
        for fname, static, border, x, y, w, h, fdata in c.frameList:
            fpadding_top = self._get_from_data(fdata, 'padding-top', padding_top, get_size)
            fpadding_left = self._get_from_data(fdata, 'padding-left', padding_left, get_size)
            fpadding_right = self._get_from_data(fdata, 'padding-right', padding_right, get_size)
            fpadding_bottom = self._get_from_data(fdata, 'padding-bottom', padding_bottom, get_size)
            fborder_color = self._get_from_data(fdata, ('border-top-color', 'border-bottom-color', 'border-left-color',
                                                        'border-right-color'), border_color, get_color)
            fborder_width = self._get_from_data(fdata, ('border-top-width', 'border-bottom-width', 'border-left-width',
                                                        'border-right-width'), border_width, get_size)

            if border or page_border:
                frame_border = ShowBoundaryValue()
            else:
                frame_border = ShowBoundaryValue(color=fborder_color, width=fborder_width)

            #fix frame sizing problem.
            if static:
                x, y, w, h = get_frame_dimensions(fdata, c.pageSize[0], c.pageSize[1])
            x, y, w, h = get_coordinates(x, y, w, h, c.pageSize)
            if w <= 0 or h <= 0:
                log.warn(self.c.warning("Negative width or height of frame. Check @frame definitions."))

            frame = Frame(
                x, y, w, h,
                id=fname,
                leftPadding=fpadding_left,
                rightPadding=fpadding_right,
                bottomPadding=fpadding_bottom,
                topPadding=fpadding_top,
                showBoundary=frame_border)

            if static:
                frame.pisaStaticStory = []
                c.frameStatic[static] = [frame] + c.frameStatic.get(static, [])
                static_list.append(frame)
            else:
                frame_list.append(frame)

        background = data.get("background-image", None)
        if background:
            #should be relative to the css file
            background = self.c.get_file(background, relative=self.c.cssParser.rootPath)

        if not frame_list:
            log.warn(c.warning("missing explicit frame definition for content or just static frames"))
            fname, static, border, x, y, w, h, data = self._pisa_add_frame(name, data, first=True, border=page_border,
                                                                         size=c.pageSize)
            x, y, w, h = get_coordinates(x, y, w, h, c.pageSize)
            if w <= 0 or h <= 0:
                log.warn(c.warning("Negative width or height of frame. Check @page definitions."))

            if border or page_border:
                frame_border = ShowBoundaryValue()
            else:
                frame_border = ShowBoundaryValue(color=border_color, width=border_width)

            frame_list.append(Frame(
                x, y, w, h,
                id=fname,
                leftPadding=padding_left,
                rightPadding=padding_right,
                bottomPadding=padding_bottom,
                topPadding=padding_top,
                showBoundary=frame_border))

        pt = PmlPageTemplate(
            id=name,
            frames=frame_list,
            pagesize=c.pageSize,
        )
        pt.pisaStaticList = static_list
        pt.pisaBackground = background
        pt.pisaBackgroundList = c.pisaBackgroundList

        if is_landscape:
            pt.pageorientation = pt.LANDSCAPE

        c.templateList[name] = pt
        c.template = None
        c.frameList = []
        c.frameStaticList = []

        return {}, {}

    def at_frame(self, name, declarations):
        if declarations:
            result = self.ruleset([self.selector('*')], declarations)
            # print "@BOX", name, declarations, result

            data = result[0]
            if data:
                try:
                    data = data.values()[0]
                except Exception:
                    data = data.popitem()[1]
                self.c.frameList.append(
                    self._pisa_add_frame(name, data, size=self.c.pageSize))

        return {}, {} # TODO: It always returns empty dicts?


class PisaCSSParser(css.CSSParser):
    def parseExternal(self, cssResourceName):

        oldRootPath = self.rootPath
        cssFile = self.c.get_file(cssResourceName, relative=self.rootPath)
        if not cssFile:
            return None
        if self.rootPath and urlparse.urlparse(self.rootPath).scheme:
            self.rootPath = urlparse.urljoin(self.rootPath, cssResourceName)
        else:
            self.rootPath = get_dir_name(cssFile.uri)

        result = self.parse(cssFile.get_data())
        self.rootPath = oldRootPath
        return result


class PisaContext(object):
    """
    Helper class for creation of reportlab story and container for
    various data.
    """

    def __init__(self, path, debug=0, capacity=-1):
        self.fontList = copy.copy(xhtml2pdf.default.DEFAULT_FONT)
        self.path = []
        self.capacity = capacity

        self.node = None
        self.toc = PmlTableOfContents()
        self.story = []
        self.indexing_story = None
        self.text = []
        self.log = []
        self.err = 0
        self.warn = 0
        self.text = u""
        self.uidctr = 0
        self.multiBuild = False

        self.pageSize = A4
        self.template = None
        self.templateList = {}

        self.frameList = []
        self.frameStatic = {}
        self.frameStaticList = []
        self.pisaBackgroundList = []

        self.keepInFrameIndex = None

        self.baseFontSize = get_size("12pt")

        self.anchorFrag = []
        self.anchorName = []

        self.tableData = None

        self.frag = self.fragBlock = get_paragraph_fragment(ParagraphStyle('default%d' % self.uid()))
        self.fragList = []
        self.fragAnchor = []
        self.fragStack = []
        self.fragStrip = True

        self.listCounter = 0

        self.cssText = ""
        self.cssDefaultText = ""

        self.image = None
        self.imageData = {}
        self.force = False

        self.path_callback = None # External callback function for path calculations

        # Store path to document
        self.pathDocument = path or "__dummy__"
        parts = urlparse.urlparse(self.pathDocument)
        if not parts.scheme:
            self.pathDocument = os.path.abspath(self.pathDocument)
        self.pathDirectory = get_dir_name(self.pathDocument)

        self.meta = dict(
            author="",
            title="",
            subject="",
            keywords="",
            pagesize=A4,
        )
        self.CSSBuilder = None
        self.CSSParser = None

    def uid(self):
        self.uidctr += 1
        return self.uidctr

    # METHODS FOR CSS
    def add_css(self, value):
        value = value.strip()
        if value.startswith("<![CDATA["):
            value = value[9: - 3]
        if value.startswith("<!--"):
            value = value[4: - 3]
        self.cssText += value.strip() + "\n"

    # METHODS FOR CSS
    def add_default_css(self, value):
        value = value.strip()
        if value.startswith("<![CDATA["):
            value = value[9: - 3]
        if value.startswith("<!--"):
            value = value[4: - 3]
        self.cssDefaultText += value.strip() + "\n"

    def parse_css(self):
        # This self-reference really should be refactored. But for now
        # we'll settle for using weak references. This avoids memory
        # leaks because the garbage collector (at least on cPython
        # 2.7.3) isn't aggressive enough.
        import weakref

        self.CSSBuilder = PisaCSSBuilder(mediumSet=["all", "print", "pdf"])
        self.CSSBuilder._c = weakref.ref(self)
        PisaCSSBuilder.c = property(lambda self: self._c())

        self.CSSParser = PisaCSSParser(self.CSSBuilder)
        self.CSSParser.rootPath = self.pathDirectory
        self.CSSParser._c = weakref.ref(self)
        PisaCSSParser.c = property(lambda self: self._c())

        self.css = self.CSSParser.parse(self.cssText)
        self.cssDefault = self.CSSParser.parse(self.cssDefaultText)
        self.cssCascade = css.CSSCascadeStrategy(userAgent=self.cssDefault, user=self.css)
        self.cssCascade.parser = self.CSSParser

    # METHODS FOR STORY
    def add_story(self, data):
        self.story.append(data)

    def swap_story(self, story=None):
        if story is None:
            story = []
        self.story, story = story, self.story
        return story

    def to_paragraph_style(self, first):
        style = ParagraphStyle('default%d' % self.uid(), keepWithNext=first.keepWithNext)
        style.fontName = first.fontName
        style.fontSize = first.fontSize
        style.letterSpacing = first.letterSpacing
        style.leading = max(first.leading + first.leadingSpace, first.fontSize * 1.25)
        style.backColor = first.backColor
        style.spaceBefore = first.spaceBefore
        style.spaceAfter = first.spaceAfter
        style.leftIndent = first.leftIndent
        style.rightIndent = first.rightIndent
        style.firstLineIndent = first.firstLineIndent
        style.textColor = first.textColor
        style.alignment = first.alignment
        style.bulletFontName = first.bulletFontName or first.fontName
        style.bulletFontSize = first.fontSize
        style.bulletIndent = first.bulletIndent
        style.wordWrap = first.wordWrap

        # Border handling for Paragraph

        # Transfer the styles for each side of the border, *not* the whole
        # border values that reportlab supports. We'll draw them ourselves in
        # PmlParagraph.
        style.borderTopStyle = first.borderTopStyle
        style.borderTopWidth = first.borderTopWidth
        style.borderTopColor = first.borderTopColor
        style.borderBottomStyle = first.borderBottomStyle
        style.borderBottomWidth = first.borderBottomWidth
        style.borderBottomColor = first.borderBottomColor
        style.borderLeftStyle = first.borderLeftStyle
        style.borderLeftWidth = first.borderLeftWidth
        style.borderLeftColor = first.borderLeftColor
        style.borderRightStyle = first.borderRightStyle
        style.borderRightWidth = first.borderRightWidth
        style.borderRightColor = first.borderRightColor

        # If no border color is given, the text color is used (XXX Tables!)
        if (style.borderTopColor is None) and style.borderTopWidth:
            style.borderTopColor = first.textColor
        if (style.borderBottomColor is None) and style.borderBottomWidth:
            style.borderBottomColor = first.textColor
        if (style.borderLeftColor is None) and style.borderLeftWidth:
            style.borderLeftColor = first.textColor
        if (style.borderRightColor is None) and style.borderRightWidth:
            style.borderRightColor = first.textColor

        style.borderPadding = first.borderPadding

        style.paddingTop = first.paddingTop
        style.paddingBottom = first.paddingBottom
        style.paddingLeft = first.paddingLeft
        style.paddingRight = first.paddingRight
        style.fontName = tt2ps(first.fontName, first.bold, first.italic)

        return style

    def add_toc(self):
        styles = []
        for i in range(20):
            self.node.attributes["class"] = "pdftoclevel%d" % i
            self.cssAttr = xhtml2pdf.parser.CSSCollect(self.node, self)
            xhtml2pdf.parser.CSS2Frag(self, {
                "margin-top": 0,
                "margin-bottom": 0,
                "margin-left": 0,
                "margin-right": 0,
            }, True)
            pstyle = self.to_paragraph_style(self.frag)
            styles.append(pstyle)

        self.toc.levelStyles = styles
        self.add_story(self.toc)
        self.indexing_story = None

    def add_page_count(self):
        if not self.multiBuild:
            self.indexing_story = PmlPageCount()
            self.multiBuild = True

    def dump_paragraph(self, frags, style):
        return

    def add_paragraph(self, force=False):

        force = (force or self.force)
        self.force = False

        # Cleanup the trail
        try:
            rfragList = reversed(self.fragList)
        except:
            # For Python 2.3 compatibility
            rfragList = copy.copy(self.fragList)
            rfragList.reverse()

        # Find maximum lead
        maxLeading = 0
        #fontSize = 0
        for frag in self.fragList:
            leading = get_size(frag.leadingSource, frag.fontSize) + frag.leadingSpace
            maxLeading = max(leading, frag.fontSize + frag.leadingSpace, maxLeading)
            frag.leading = leading

        if force or (self.text.strip() and self.fragList):

            # Update paragraph style by style of first fragment
            first = self.fragBlock
            style = self.to_paragraph_style(first)
            # style.leading = first.leading + first.leadingSpace
            if first.leadingSpace:
                style.leading = maxLeading
            else:
                style.leading = get_size(first.leadingSource, first.fontSize) + first.leadingSpace

            bulletText = copy.copy(first.bulletText)
            first.bulletText = None

            # Add paragraph to story
            if force or len(self.fragAnchor + self.fragList) > 0:

                # We need this empty fragment to work around problems in
                # Reportlab paragraphs regarding backGround etc.
                if self.fragList:
                    self.fragList.append(self.fragList[- 1].clone(text=''))
                else:
                    blank = self.frag.clone()
                    blank.fontName = "Helvetica"
                    blank.text = ''
                    self.fragList.append(blank)

                self.dump_paragraph(self.fragAnchor + self.fragList, style)
                para = PmlParagraph(
                    self.text,
                    style,
                    frags=self.fragAnchor + self.fragList,
                    bulletText=bulletText)

                para.outline = first.outline
                para.outlineLevel = first.outlineLevel
                para.outlineOpen = first.outlineOpen
                para.keepWithNext = first.keepWithNext
                para.autoLeading = "max"

                if self.image:
                    para = PmlParagraphAndImage(
                        para,
                        self.image,
                        side=self.imageData.get("align", "left"))

                self.add_story(para)

            self.fragAnchor = []
            first.bulletText = None

        # Reset data

        self.image = None
        self.imageData = {}

        self.clear_fragment()

    # METHODS FOR FRAG
    def clear_fragment(self):
        self.fragList = []
        self.fragStrip = True
        self.text = u""

    def copy_fragment(self, **kw):
        return self.frag.clone(**kw)

    def new_fragment(self, **kw):
        self.frag = self.frag.clone(**kw)
        return self.frag

    def _append_fragment(self, frag):
        if frag.link and frag.link.startswith("#"):
            self.anchorFrag.append((frag, frag.link[1:]))
        self.fragList.append(frag)

    # XXX Argument frag is useless!
    def add_fragment(self, text="", frag=None):

        frag = baseFrag = self.frag.clone()

        # if sub and super are both on they will cancel each other out
        if frag.sub == 1 and frag.super == 1:
            frag.sub = 0
            frag.super = 0

        # XXX Has to be replaced by CSS styles like vertical-align and font-size
        if frag.sub:
            frag.rise = - frag.fontSize * subFraction
            frag.fontSize = max(frag.fontSize - sizeDelta, 3)
        elif frag.super:
            frag.rise = frag.fontSize * superFraction
            frag.fontSize = max(frag.fontSize - sizeDelta, 3)

       # bold, italic, and underline
        frag.fontName = frag.bulletFontName = tt2ps(frag.fontName, frag.bold, frag.italic)

        # Replace &shy; with empty and normalize NBSP
        text = (text
                .replace(u"\xad", u"")
                .replace(u"\xc2\xa0", NBSP)
                .replace(u"\xa0", NBSP))

        if frag.whiteSpace == "pre":

            # Handle by lines
            for text in re.split(r'(\r\n|\n|\r)', text):
                # This is an exceptionally expensive piece of code
                self.text += text
                if ("\n" in text) or ("\r" in text):
                    # If EOL insert a linebreak
                    frag = baseFrag.clone()
                    frag.text = ""
                    frag.lineBreak = 1
                    self._append_fragment(frag)
                else:
                    # Handle tabs in a simple way
                    text = text.replace(u"\t", 8 * u" ")
                    # Somehow for Reportlab NBSP have to be inserted
                    # as single character fragments
                    for text in re.split(r'(\ )', text):
                        frag = baseFrag.clone()
                        if text == " ":
                            text = NBSP
                        frag.text = text
                        self._append_fragment(frag)
        else:
            for text in re.split(u'(' + NBSP + u')', text):
                frag = baseFrag.clone()
                if text == NBSP:
                    self.force = True
                    frag.text = NBSP
                    self.text += text
                    self._append_fragment(frag)
                else:
                    frag.text = " ".join(("x" + text + "x").split())[1: - 1]
                    if self.fragStrip:
                        frag.text = frag.text.lstrip()
                        if frag.text:
                            self.fragStrip = False
                    self.text += frag.text
                    self._append_fragment(frag)

    def push_fragment(self):
        self.fragStack.append(self.frag)
        self.new_fragment()

    def pull_fragment(self):
        self.frag = self.fragStack.pop()

    # XXX
    def _get_fragment(self, l=20):
        try:
            return repr(" ".join(self.node.toxml().split()[:l]))
        except:
            return ""

    def _get_line_number(self):
        return 0  # FIXME

    def context(self, msg):
        return "%s\n%s" % (
            str(msg),
            self._get_fragment(50))

    def warning(self, msg, *args):
        self.warn += 1
        self.log.append((xhtml2pdf.default.PML_WARNING, self._get_line_number(), str(msg), self._get_fragment(50)))
        try:
            return self.context(msg % args)
        except:
            return self.context(msg)

    def error(self, msg, *args):
        self.err += 1
        self.log.append((xhtml2pdf.default.PML_ERROR, self._get_line_number(), str(msg), self._get_fragment(50)))
        try:
            return self.context(msg % args)
        except:
            return self.context(msg)

    # UTILS
    def _get_file_deprecated(self, name, relative):
        try:
            path = relative or self.pathDirectory
            if name.startswith("data:"):
                return name
            if self.path_callback is not None:
                nv = self.path_callback(name, relative)
            else:
                if path is None:
                    log.warn("Could not find main directory for getting filename. Use CWD")
                    path = os.getcwd()
                nv = os.path.normpath(os.path.join(path, name))
                if not (nv and os.path.isfile(nv)):
                    nv = None
            if nv is None:
                log.warn(self.warning("File '%s' does not exist", name))
            return nv
        except:
            log.warn(self.warning("getFile %r %r %r", name, relative, path), exc_info=1)

    def get_file(self, name, relative=None):
        """
        Returns a file name or None
        """
        if self.path_callback is not None:
            return get_file(self._get_file_deprecated(name, relative))
        return get_file(name, relative or self.pathDirectory)

    def get_font_name(self, names, default="helvetica"):
        """
        Name of a font
        """
        # print names, self.fontList
        if not isinstance(names, ListType):
            if not isinstance(names, text_type):
                names = str(names)
            names = names.strip().split(",")
        for name in names:
            if not isinstance(name, text_type):
                name = str(name)
            font = self.fontList.get(name.strip().lower(), None)
            if font is not None:
                return font
        return self.fontList.get(default, None)

    def register_font(self, fontname, alias=None):
        if alias is None:
            alias = []
        self.fontList[str(fontname).lower()] = str(fontname)
        for a in alias:
            if not isinstance(fontname, text_type):
                fontname = str(fontname)
            self.fontList[str(a)] = fontname

    def load_font(self, names, src, encoding="WinAnsiEncoding", bold=0, italic=0):

        # XXX Just works for local filenames!
        if names and src:

            file = src
            src = file.uri

            log.debug("Load font %r", src)

            if type(names) is ListType:
                font_alias = names
            else:
                font_alias = (x.lower().strip() for x in names.split(",") if x)

            # XXX Problems with unicode here
            font_alias = [str(x) for x in font_alias]

            font_name = font_alias[0]
            parts = src.split(".")
            base_name, suffix = ".".join(parts[: - 1]), parts[- 1]
            suffix = suffix.lower()

            if suffix in ["ttc", "ttf"]:

                # determine full font name according to weight and style
                full_font_name = "%s_%d%d" % (font_name, bold, italic)

                # check if font has already been registered
                if full_font_name in self.fontList:
                    log.warn(self.warning("Repeated font embed for %s, skip new embed ", full_font_name))
                else:

                    # Register TTF font and special name
                    filename = file.get_named_file()
                    pdfmetrics.registerFont(TTFont(full_font_name, filename))

                    # Add or replace missing styles
                    for bold in (0, 1):
                        for italic in (0, 1):
                            if ("%s_%d%d" % (font_name, bold, italic)) not in self.fontList:
                                addMapping(font_name, bold, italic, full_font_name)

                    # Register "normal" name and the place holder for style
                    self.register_font(font_name, font_alias + [full_font_name])

            elif suffix in ("afm", "pfb"):

                if suffix == "afm":
                    afm = file.get_named_file()
                    tfile = PisaFileObject(base_name + ".pfb")
                    pfb = tfile.get_named_file()
                else:
                    pfb = file.get_named_file()
                    tfile = PisaFileObject(base_name + ".afm")
                    afm = tfile.get_named_file()

                # determine full font name according to weight and style
                full_font_name = "%s_%d%d" % (font_name, bold, italic)

                # check if font has already been registered
                if full_font_name in self.fontList:
                    log.warn(self.warning("Repeated font embed for %s, skip new embed", font_name))
                else:

                    # Include font
                    face = pdfmetrics.EmbeddedType1Face(afm, pfb)
                    font_name_original = face.name
                    pdfmetrics.registerTypeFace(face)
                    # print fontName, fontNameOriginal, fullFontName
                    just_font = pdfmetrics.Font(full_font_name, font_name_original, encoding)
                    pdfmetrics.registerFont(just_font)

                    # Add or replace missing styles
                    for bold in (0, 1):
                        for italic in (0, 1):
                            if ("%s_%d%d" % (font_name, bold, italic)) not in self.fontList:
                                addMapping(font_name, bold, italic, font_name_original)

                    # Register "normal" name and the place holder for style
                    self.register_font(font_name, font_alias + [full_font_name, font_name_original])
            else:
                log.warning(self.warning("wrong attributes for <pdf:font>"))

