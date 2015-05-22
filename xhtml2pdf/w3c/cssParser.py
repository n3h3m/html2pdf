# -*- coding: utf-8 -*-
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~ Copyright (C) 2002-2004  TechGame Networks, LLC.
# ~
# ~ This library is free software; you can redistribute it and/or
# ~ modify it under the terms of the BSD style License as found in the
# ~ LICENSE file included with this distribution.
#
#  Modified by Dirk Holtwick <holtwick@web.de>, 2007-2008
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

"""
CSS-2.1 parser
~~~~~~~~~~~~~~

The CSS 2.1 Specification this parser was derived from can be found at http://www.w3.org/TR/CSS21/

Primary Classes:
    * CSSParser
        Parses CSS source forms into results using a Builder Pattern.  Must
        provide concrete implementation of CSSBuilderAbstract.

    * CSSBuilderAbstract
        Outlines the interface between CSSParser and it's rule-builder.
        Compose CSSParser with a concrete implementation of the builder to get
        usable results from the CSS parser.

Dependencies:
    python 2.3 (or greater)
    re
"""

import re
import six

from xhtml2pdf.w3c.cssSpecial import cleanup_css


def is_at_rule_ident(src, ident):
    """

    :param src:
    :param ident:
    :return:
    """
    return re.match(r'^@' + ident + r'\s*', src)


def strip_at_rule_ident(src):
    """

    :param src:
    :return:
    """
    return re.sub(r'^@[a-z\-]+\s*', '', src)


class CSSSelectorAbstract(object):
    """Outlines the interface between CSSParser and it's rule-builder for selectors.

    CSSBuilderAbstract.selector and CSSBuilderAbstract.combineSelectors must
    return concrete implementations of this abstract.

    See css.CSSMutableSelector for an example implementation.
    """
    def add_hash_id(self, hashId):
        raise NotImplementedError('Subclass responsibility')

    def add_class(self, class_):
        raise NotImplementedError('Subclass responsibility')

    def add_attribute(self, attrName):
        raise NotImplementedError('Subclass responsibility')

    def add_attribute_operation(self, attrName, op, attrValue):
        raise NotImplementedError('Subclass responsibility')

    def add_pseudo(self, name):
        raise NotImplementedError('Subclass responsibility')

    def add_pseudo_function(self, name, value):
        raise NotImplementedError('Subclass responsibility')


class CSSBuilderAbstract(object):
    """
    Outlines the interface between CSSParser and it's rule-builder.  Compose
    CSSParser with a concrete implementation of the builder to get usable
    results from the CSS parser.

    See css.CSSBuilder for an example implementation
    """
    def set_charset(self, charset):
        raise NotImplementedError('Subclass responsibility')

    # ~ css results ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def begin_stylesheet(self):
        raise NotImplementedError('Subclass responsibility')

    def stylesheet(self, elements):
        raise NotImplementedError('Subclass responsibility')

    def end_stylesheet(self):
        raise NotImplementedError('Subclass responsibility')

    def begin_inline(self):
        raise NotImplementedError('Subclass responsibility')

    def inline(self, declarations):
        raise NotImplementedError('Subclass responsibility')

    def end_inline(self):
        raise NotImplementedError('Subclass responsibility')

    def ruleset(self, selectors, declarations):
        raise NotImplementedError('Subclass responsibility')

    # ~ css namespaces ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def resolve_namespace_prefix(self, nsPrefix, name):
        raise NotImplementedError('Subclass responsibility')

    # ~ css @ directives ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def at_charset(self, charset):
        raise NotImplementedError('Subclass responsibility')

    def at_import(self, import_, mediums, cssParser):
        raise NotImplementedError('Subclass responsibility')

    def at_namespace(self, nsPrefix, uri):
        raise NotImplementedError('Subclass responsibility')

    def at_media(self, mediums, ruleset):
        raise NotImplementedError('Subclass responsibility')

    def at_page(self, page, pseudopage, declarations):
        raise NotImplementedError('Subclass responsibility')

    def at_font_face(self, declarations):
        raise NotImplementedError('Subclass responsibility')

    def at_ident(self, atIdent, cssParser, src):
        return src, NotImplemented

    # ~ css selectors ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def combine_selectors(self, selectorA, combiner, selectorB):
        """Return value must implement CSSSelectorAbstract"""
        raise NotImplementedError('Subclass responsibility')

    def selector(self, name):
        """Return value must implement CSSSelectorAbstract"""
        raise NotImplementedError('Subclass responsibility')

    # ~ css declarations ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def property(self, name, value, important=False):
        raise NotImplementedError('Subclass responsibility')

    def combine_terms(self, termA, combiner, termB):
        raise NotImplementedError('Subclass responsibility')

    def term_ident(self, value):
        raise NotImplementedError('Subclass responsibility')

    def term_number(self, value, units=None):
        raise NotImplementedError('Subclass responsibility')

    def term_rgb(self, value):
        raise NotImplementedError('Subclass responsibility')

    def term_uri(self, value):
        raise NotImplementedError('Subclass responsibility')

    def term_string(self, value):
        raise NotImplementedError('Subclass responsibility')

    def term_unicode_range(self, value):
        raise NotImplementedError('Subclass responsibility')

    def term_function(self, name, value):
        raise NotImplementedError('Subclass responsibility')

    def term_unknown(self, src):
        raise NotImplementedError('Subclass responsibility')

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~ CSS Parser
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class CSSParseError(Exception):
    src = None
    ctxsrc = None
    fullsrc = None
    inline = False
    srcCtxIdx = None
    srcFullIdx = None
    ctxsrcFullIdx = None

    def __init__(self, msg, src, ctxsrc=None):
        super(Exception, self).__init__(msg)
        self.src = src
        self.ctxsrc = ctxsrc or src
        if self.ctxsrc:
            self.srcCtxIdx = self.ctxsrc.find(self.src)
            if self.srcCtxIdx < 0:
                del self.srcCtxIdx

    def __str__(self):
        if self.ctxsrc:
            return "{0}:: ({1}, {2})".format(super(Exception, self).__str__(),
                                             repr(self.ctxsrc[:self.srcCtxIdx]),
                                             repr(self.ctxsrc[self.srcCtxIdx:self.srcCtxIdx + 20]))
        else:
            return "{0}:: {1}".format(super(Exception, self).__str__(), repr(self.src[:40]))

    def setFullCSSSource(self, fullsrc, inline=False):
        self.fullsrc = fullsrc
        if inline:
            self.inline = inline
        if self.fullsrc:
            self.srcFullIdx = self.fullsrc.find(self.src)
            if self.srcFullIdx < 0:
                del self.srcFullIdx
            self.ctxsrcFullIdx = self.fullsrc.find(self.ctxsrc)
            if self.ctxsrcFullIdx < 0:
                del self.ctxsrcFullIdx

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class CSSParser(object):
    """
    CSS-2.1 parser dependent only upon the re module.

    Implemented directly from http://www.w3.org/TR/CSS21/grammar.html
    Tested with some existing CSS stylesheets for portability.

    CSS Parsing API:
        * setCSSBuilder()
            To set your concrete implementation of CSSBuilderAbstract

        * parseFile()
            Use to parse external stylesheets using a file-like object::

                >>> cssFile = open('test.css', 'r')
                >>> stylesheets = myCSSParser.parse_file(cssFile)

        * parse()
            Use to parse embedded stylesheets using source string::

                >>> cssSrc = '''
                    body,body.body {
                        font: 110%, "Times New Roman", Arial, Verdana, Helvetica, serif;
                        background: White;
                        color: Black;
                    }
                    a {text-decoration: underline;}
                '''
                >>> stylesheets = myCSSParser.parse(cssSrc)

        * parseInline()
            Use to parse inline stylesheets using attribute source string::

                >>> style = 'font: 110%, "Times New Roman", Arial, Verdana, Helvetica, serif; background: White; color: Black'
                >>> stylesheets = myCSSParser.parse_inline(style)

        * parseAttributes()
            Use to parse attribute string values into inline stylesheets::

                >>> stylesheets = myCSSParser.parse_attributes(
                        font='110%, "Times New Roman", Arial, Verdana, Helvetica, serif',
                        background='White',
                        color='Black')

        * parseSingleAttr()
            Use to parse a single string value into a CSS expression::

                >>> fontValue = myCSSParser.parse_single_attr('110%, "Times New Roman", Arial, Verdana, Helvetica, serif')
    """

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # ~ Constants / Variables / Etc.
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    ParseError = CSSParseError

    attribute_operators = ['=', '~=', '|=', '&=', '^=', '!=', '<>']
    selector_qualifiers = ('#', '.', '[', ':')
    selector_combiners = ['+', '>']
    expression_operators = ('/', '+', ',')

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # ~ Regular expressions
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    _orRule = lambda *args: '|'.join(args)
    _reflags = re.I | re.M | re.U
    i_hex = '[0-9a-fA-F]'
    i_nonascii = u'[\200-\377]'
    i_unicode = '\\\\(?:%s){1,6}\s?' % i_hex
    i_escape = _orRule(i_unicode, u'\\\\[ -~\200-\377]')
    # i_nmstart = _orRule('[A-Za-z_]', i_nonascii, i_escape)
    i_nmstart = _orRule('\-[^0-9]|[A-Za-z_]', i_nonascii,
                        i_escape) # XXX Added hyphen, http://www.w3.org/TR/CSS21/syndata.html#value-def-identifier
    i_nmchar = _orRule('[-0-9A-Za-z_]', i_nonascii, i_escape)
    i_ident = '((?:%s)(?:%s)*)' % (i_nmstart, i_nmchar)
    re_ident = re.compile(i_ident, _reflags)
    # Caution: treats all characters above 0x7f as legal for an identifier.
    i_unicodeid = r'([^\u0000-\u007f]+)'
    re_unicodeid = re.compile(i_unicodeid, _reflags)
    i_element_name = '((?:%s)|\*)' % (i_ident[1:-1],)
    re_element_name = re.compile(i_element_name, _reflags)
    i_namespace_selector = '((?:%s)|\*|)\|(?!=)' % (i_ident[1:-1],)
    re_namespace_selector = re.compile(i_namespace_selector, _reflags)
    i_class = '\\.' + i_ident
    re_class = re.compile(i_class, _reflags)
    i_hash = '#((?:%s)+)' % i_nmchar
    re_hash = re.compile(i_hash, _reflags)
    i_rgbcolor = '(#%s{6}|#%s{3})' % (i_hex, i_hex)
    re_rgbcolor = re.compile(i_rgbcolor, _reflags)
    i_nl = u'\n|\r\n|\r|\f'
    i_escape_nl = u'\\\\(?:%s)' % i_nl
    i_string_content = _orRule(u'[\t !#$%&(-~]', i_escape_nl, i_nonascii, i_escape)
    i_string1 = u'\"((?:%s|\')*)\"' % i_string_content
    i_string2 = u'\'((?:%s|\")*)\'' % i_string_content
    i_string = _orRule(i_string1, i_string2)
    re_string = re.compile(i_string, _reflags)
    i_uri = (u'url\\(\s*(?:(?:%s)|((?:%s)+))\s*\\)'
             % (i_string, _orRule('[!#$%&*-~]', i_nonascii, i_escape)))
    # XXX For now
    # i_uri = u'(url\\(.*?\\))'
    re_uri = re.compile(i_uri, _reflags)
    i_num = u'(([-+]?[0-9]+(?:\\.[0-9]+)?)|([-+]?\\.[0-9]+))' # XXX Added out paranthesis, because e.g. .5em was not parsed correctly
    re_num = re.compile(i_num, _reflags)
    i_unit = '(%%|%s)?' % i_ident
    re_unit = re.compile(i_unit, _reflags)
    i_function = i_ident + '\\('
    re_function = re.compile(i_function, _reflags)
    i_functionterm = u'[-+]?' + i_function
    re_functionterm = re.compile(i_functionterm, _reflags)
    i_unicoderange1 = "(?:U\\+%s{1,6}-%s{1,6})" % (i_hex, i_hex)
    i_unicoderange2 = "(?:U\\+\?{1,6}|{h}(\?{0,5}|{h}(\?{0,4}|{h}(\?{0,3}|{h}(\?{0,2}|{h}(\??|{h}))))))"
    i_unicoderange = i_unicoderange1 # u'(%s|%s)' % (i_unicoderange1, i_unicoderange2)
    re_unicoderange = re.compile(i_unicoderange, _reflags)

    # i_comment = u'(?:\/\*[^*]*\*+([^/*][^*]*\*+)*\/)|(?://.*)'
    # gabriel: only C convention for comments is allowed in CSS
    i_comment = u'(?:\/\*[^*]*\*+([^/*][^*]*\*+)*\/)'
    re_comment = re.compile(i_comment, _reflags)
    i_important = u'!\s*(important)'
    re_important = re.compile(i_important, _reflags)
    del _orRule

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # ~ Public
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def __init__(self, css_builder=None):
        self._css_builder = css_builder

    # ~ CSS Builder to delegate to ~~~~~~~~~~~~~~~~~~~~~~~~

    @property
    def css_builder(self):
        """A concrete instance implementing CSSBuilderAbstract"""
        return self._css_builder

    @css_builder.setter
    def css_builder(self, value):
        """A concrete instance implementing CSSBuilderAbstract"""
        self._css_builder = value

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # ~ Public CSS Parsing API
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def parse_file(self, srcFile, closeFile=False):
        """Parses CSS file-like objects using the current cssBuilder.
        Use for external stylesheets."""

        try:
            result = self.parse(srcFile.read())
        finally:
            if closeFile:
                srcFile.close()
        return result

    def parse(self, src):
        """

        Parses CSS string source using the current cssBuilder.

        Use for embedded stylesheets.

        :param src:
        :type src: str
        """

        self.css_builder.begin_stylesheet()
        if not isinstance(src, six.text_type):
            src = src.decode()  # FIXME use text from the get-go
        assert isinstance(src, six.text_type), "'src' must be text!"
        try:
            # XXX Some simple preprocessing
            src = cleanup_css(src)
            try:
                src, stylesheet = self._parse_stylesheet(src)
            except self.ParseError as err:
                err.setFullCSSSource(src)
                raise
        finally:
            self.css_builder.end_stylesheet()
        return stylesheet

    def parse_inline(self, src):
        """Parses CSS inline source string using the current cssBuilder.
        Use to parse a tag's 'style'-like attribute."""
        self.css_builder.begin_inline()
        try:
            try:
                src, properties = self._parse_declaration_group(src.strip(), braces=False)
            except self.ParseError as err:
                err.setFullCSSSource(src, inline=True)
                raise

            result = self.css_builder.inline(properties)
        finally:
            self.css_builder.end_inline()
        return result

    def parse_attributes(self, attributes=None, **kwAttributes):
        """Parses CSS attribute source strings, and return as an inline stylesheet.
        Use to parse a tag's highly CSS-based attributes like 'font'.

        See also: parseSingleAttr
        """
        if attributes is None:
            attributes = {}
        if attributes:
            kwAttributes.update(attributes)

        self.css_builder.begin_inline()
        try:
            properties = []
            for propertyName, src in kwAttributes.items():
                try:
                    src, property = self._parse_declaration_property(src.strip(), propertyName)
                    properties.append(property)
                except self.ParseError as err:
                    err.setFullCSSSource(src, inline=True)
                    raise
            result = self.css_builder.inline(properties)
        finally:
            self.css_builder.end_inline()
        return result

    def parse_single_attr(self, attrValue):
        """Parse a single CSS attribute source string, and returns the built CSS expression.
        Use to parse a tag's highly CSS-based attributes like 'font'.

        See also: parseAttributes
        """

        results = self.parse_attributes(temp=attrValue)
        if 'temp' in results[1]:
            return results[1]['temp']
        else:
            return results[0]['temp']

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # ~ Internal _parse methods
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _parse_stylesheet(self, src):
        """stylesheet
        : [ CHARSET_SYM S* STRING S* ';' ]?
            [S|CDO|CDC]* [ import [S|CDO|CDC]* ]*
            [ [ ruleset | media | page | font_face ] [S|CDO|CDC]* ]*
        ;
        """
        # Get rid of the comments
        src = self.re_comment.sub(six.u(''), src)

        # [ CHARSET_SYM S* STRING S* ';' ]?
        src = self._parse_at_charset(src)

        # [S|CDO|CDC]*
        src = self._parse_s_cdo_cdc(src)
        #  [ import [S|CDO|CDC]* ]*
        src, stylesheet_imports = self._parse_at_imports(src)

        # [ namespace [S|CDO|CDC]* ]*
        src = self._parse_at_namespace(src)

        stylesheet_elements = []

        # [ [ ruleset | atkeywords ] [S|CDO|CDC]* ]*
        while src:  # due to ending with ]*
            if src.startswith('@'):
                # @media, @page, @font-face
                src, at_results = self._parse_at_keyword(src)
                if at_results is not None and at_results != NotImplemented:
                    stylesheet_elements.extend(at_results)
            else:
                # ruleset
                src, ruleset = self._parse_ruleset(src)
                stylesheet_elements.append(ruleset)

            # [S|CDO|CDC]*
            src = self._parse_s_cdo_cdc(src)

        stylesheet = self.css_builder.stylesheet(stylesheet_elements, stylesheet_imports)
        return src, stylesheet

    def _parse_s_cdo_cdc(self, src):
        """[S|CDO|CDC]*"""
        while True:
            src = src.lstrip()
            if src.startswith('<!--'):
                src = src[4:]
            elif src.startswith('-->'):
                src = src[3:]
            else:
                break
        return src

    # ~ CSS @ directives ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _parse_at_charset(self, src):
        """[ CHARSET_SYM S* STRING S* ';' ]?"""
        if is_at_rule_ident(src, 'charset'):
            ctxsrc = src
            src = strip_at_rule_ident(src)
            charset, src = self._get_string(src)
            src = src.lstrip()
            if src[:1] != ';':
                raise self.ParseError('@charset expected a terminating \';\'', src, ctxsrc)
            src = src[1:].lstrip()

            self.css_builder.at_charset(charset)
        return src

    def _parse_at_imports(self, src):
        """[ import [S|CDO|CDC]* ]*"""
        result = []
        while is_at_rule_ident(src, 'import'):
            ctxsrc = src
            src = strip_at_rule_ident(src)

            import_, src = self._get_string_or_uri(src)
            if import_ is None:
                raise self.ParseError('Import expecting string or url', src, ctxsrc)

            mediums = []
            medium, src = self._get_ident(src.lstrip())
            while medium is not None:
                mediums.append(medium)
                if src[:1] == ',':
                    src = src[1:].lstrip()
                    medium, src = self._get_ident(src)
                else:
                    break

            # XXX No medium inherits and then "all" is appropriate
            if not mediums:
                mediums = ["all"]

            if src[:1] != ';':
                raise self.ParseError('@import expected a terminating \';\'', src, ctxsrc)
            src = src[1:].lstrip()

            stylesheet = self.css_builder.at_import(import_, mediums, self)
            if stylesheet is not None:
                result.append(stylesheet)

            src = self._parse_s_cdo_cdc(src)
        return src, result

    def _parse_at_namespace(self, src):
        """namespace :

        @namespace S* [IDENT S*]? [STRING|URI] S* ';' S*
        """

        src = self._parse_s_cdo_cdc(src)
        while is_at_rule_ident(src, 'namespace'):
            ctxsrc = src
            src = strip_at_rule_ident(src)

            namespace, src = self._get_string_or_uri(src)
            if namespace is None:
                nsPrefix, src = self._get_ident(src)
                if nsPrefix is None:
                    raise self.ParseError('@namespace expected an identifier or a URI', src, ctxsrc)
                namespace, src = self._get_string_or_uri(src.lstrip())
                if namespace is None:
                    raise self.ParseError('@namespace expected a URI', src, ctxsrc)
            else:
                nsPrefix = None

            src = src.lstrip()
            if src[:1] != ';':
                raise self.ParseError('@namespace expected a terminating \';\'', src, ctxsrc)
            src = src[1:].lstrip()

            self.css_builder.at_namespace(nsPrefix, namespace)

            src = self._parse_s_cdo_cdc(src)
        return src

    def _parse_at_keyword(self, src):
        """[media | page | font_face | unknown_keyword]"""
        ctxsrc = src
        if is_at_rule_ident(src, 'media'):
            src, result = self._parse_at_media(src)
        elif is_at_rule_ident(src, 'page'):
            src, result = self._parse_at_page(src)
        elif is_at_rule_ident(src, 'font-face'):
            src, result = self._parse_at_font_face(src)
        # XXX added @import, was missing!
        elif is_at_rule_ident(src, 'import'):
            src, result = self._parse_at_imports(src)
        elif is_at_rule_ident(src, 'frame'):
            src, result = self._parse_at_frame(src)
        elif src.startswith('@'):
            src, result = self._parse_at_ident(src)
        else:
            raise self.ParseError('Unknown state in atKeyword', src, ctxsrc)
        return src, result

    def _parse_at_media(self, src):
        """media
        : MEDIA_SYM S* medium [ ',' S* medium ]* '{' S* ruleset* '}' S*
        ;
        """
        ctxsrc = src
        src = src[len('@media '):].lstrip()
        mediums = []
        while src and src[0] != '{':
            medium, src = self._get_ident(src)
            if medium is None:
                raise self.ParseError('@media rule expected media identifier', src, ctxsrc)
            # make "and ... {" work
            if medium == u'and':
                # strip up to curly bracket
                pattern = re.compile('.*({.*)')
                match = re.match(pattern, src)
                src = src[match.end()-1:]
                break
            mediums.append(medium)
            if src[0] == ',':
                src = src[1:].lstrip()
            else:
                src = src.lstrip()

        if not src.startswith('{'):
            raise self.ParseError('Ruleset opening \'{\' not found', src, ctxsrc)
        src = src[1:].lstrip()

        stylesheet_elements = []
        # while src and not src.startswith('}'):
        #    src, ruleset = self._parseRuleset(src)
        #    stylesheetElements.append(ruleset)
        #    src = src.lstrip()

        # Containing @ where not found and parsed
        while src and not src.startswith('}'):
            if src.startswith('@'):
                # @media, @page, @font-face
                src, atResults = self._parse_at_keyword(src)
                if atResults is not None:
                    stylesheet_elements.extend(atResults)
            else:
                # ruleset
                src, ruleset = self._parse_ruleset(src)
                stylesheet_elements.append(ruleset)
            src = src.lstrip()

        if not src.startswith('}'):
            raise self.ParseError('Ruleset closing \'}\' not found', src, ctxsrc)
        else:
            src = src[1:].lstrip()

        result = self.css_builder.at_media(mediums, stylesheet_elements)
        return src, result

    def _parse_at_page(self, src):
        """page
        : PAGE_SYM S* IDENT? pseudo_page? S*
            '{' S* declaration [ ';' S* declaration ]* '}' S*
        ;
        """
        ctxsrc = src
        src = src[len('@page '):].lstrip()
        page, src = self._get_ident(src)
        if src[:1] == ':':
            pseudopage, src = self._get_ident(src[1:])
            page = page + '_' + pseudopage
        else:
            pseudopage = None

        # src, properties = self._parseDeclarationGroup(src.lstrip())

        # Containing @ where not found and parsed
        stylesheet_elements = []
        src = src.lstrip()
        properties = []

        # XXX Extended for PDF use
        if not src.startswith('{'):
            raise self.ParseError('Ruleset opening \'{\' not found', src, ctxsrc)
        else:
            src = src[1:].lstrip()

        while src and not src.startswith('}'):
            if src.startswith('@'):
                # @media, @page, @font-face
                src, at_results = self._parse_at_keyword(src)
                if at_results is not None:
                    stylesheet_elements.extend(at_results)
            else:
                src, nproperties = self._parse_declaration_group(src.lstrip(), braces=False)
                properties += nproperties
            src = src.lstrip()

        result = [self.css_builder.at_page(page, pseudopage, properties)]

        return src[1:].lstrip(), result

    def _parse_at_frame(self, src):
        """
        XXX Proprietary for PDF
        """
        ctxsrc = src
        src = src[len('@frame '):].lstrip()
        box, src = self._get_ident(src)
        src, properties = self._parse_declaration_group(src.lstrip())
        result = [self.css_builder.at_frame(box, properties)]
        return src.lstrip(), result

    def _parse_at_font_face(self, src):
        ctxsrc = src
        src = src[len('@font-face '):].lstrip()
        src, properties = self._parse_declaration_group(src)
        result = [self.css_builder.at_font_face(properties)]
        return src, result

    def _parse_at_ident(self, src):
        ctxsrc = src
        atIdent, src = self._get_ident(src[1:])
        if atIdent is None:
            raise self.ParseError('At-rule expected an identifier for the rule', src, ctxsrc)

        src, result = self.css_builder.at_ident(atIdent, self, src)

        if result is NotImplemented:
            # An at-rule consists of everything up to and including the next semicolon (;) or the next block,
            # whichever comes first

            semiIdx = src.find(';')
            if semiIdx < 0:
                semiIdx = None
            blockIdx = src[:semiIdx].find('{')
            if blockIdx < 0:
                blockIdx = None

            if semiIdx is not None and semiIdx < blockIdx:
                src = src[semiIdx + 1:].lstrip()
            elif blockIdx is None:
                # consume the rest of the content since we didn't find a block or a semicolon
                src = src[-1:-1]
            elif blockIdx is not None:
                # expecing a block...
                src = src[blockIdx:]
                try:
                    # try to parse it as a declarations block
                    src, declarations = self._parse_declaration_group(src)
                except self.ParseError:
                    # try to parse it as a stylesheet block
                    src, stylesheet = self._parse_stylesheet(src)
            else:
                raise self.ParseError('Unable to ignore @-rule block', src, ctxsrc)

        return src.lstrip(), result

    # ~ ruleset - see selector and declaration groups ~~~~

    def _parse_ruleset(self, src):
        """ruleset
        : selector [ ',' S* selector ]*
            '{' S* declaration [ ';' S* declaration ]* '}' S*
        ;
        """
        src, selectors = self._parse_selector_group(src)
        src, properties = self._parse_declaration_group(src.lstrip())
        result = self.css_builder.ruleset(selectors, properties)
        return src, result

    # ~ selector parsing ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _parse_selector_group(self, src):
        selectors = []
        while src[:1] not in ('{', '}', ']', '(', ')', ';', ''):
            src, selector = self._parse_selector(src)
            if selector is None:
                break
            selectors.append(selector)
            if src.startswith(','):
                src = src[1:].lstrip()
        return src, selectors

    def _parse_selector(self, src):
        """selector
        : simple_selector [ combinator simple_selector ]*
        ;
        """
        src, selector = self._parse_simple_selector(src)
        srcLen = len(src) # XXX
        while src[:1] not in ('', ',', ';', '{', '}', '[', ']', '(', ')'):
            for combiner in self.selector_combiners:
                if src.startswith(combiner):
                    src = src[len(combiner):].lstrip()
                    break
            else:
                combiner = ' '
            src, selectorB = self._parse_simple_selector(src)

            # XXX Fix a bug that occured here e.g. : .1 {...}
            if len(src) >= srcLen:
                src = src[1:]
                while src and (src[:1] not in ('', ',', ';', '{', '}', '[', ']', '(', ')')):
                    src = src[1:]
                return src.lstrip(), None

            selector = self.css_builder.combine_selectors(selector, combiner, selectorB)

        return src.lstrip(), selector

    def _parse_simple_selector(self, src):
        """simple_selector
        : [ namespace_selector ]? element_name? [ HASH | class | attrib | pseudo ]* S*
        ;
        """
        ctxsrc = src.lstrip()
        nsPrefix, src = self._get_match_result(self.re_namespace_selector, src)
        name, src = self._get_match_result(self.re_element_name, src)
        if name:
            pass # already *successfully* assigned
        elif src[:1] in self.selector_qualifiers:
            name = '*'
        else:
            raise self.ParseError('Selector name or qualifier expected', src, ctxsrc)

        name = self.css_builder.resolve_namespace_prefix(nsPrefix, name)
        selector = self.css_builder.selector(name)
        while src and src[:1] in self.selector_qualifiers:
            hash_, src = self._get_match_result(self.re_hash, src)
            if hash_ is not None:
                selector.add_hash_id(hash_)
                continue

            class_, src = self._get_match_result(self.re_class, src)
            if class_ is not None:
                selector.add_class(class_)
                continue

            if src.startswith('['):
                src, selector = self._parse_selector_attribute(src, selector)
            elif src.startswith(':'):
                src, selector = self._parse_selector_pseudo(src, selector)
            else:
                break

        return src.lstrip(), selector

    def _parse_selector_attribute(self, src, selector):
        """attrib
        : '[' S* [ namespace_selector ]? IDENT S* [ [ '=' | INCLUDES | DASHMATCH ] S*
            [ IDENT | STRING ] S* ]? ']'
        ;
        """
        ctxsrc = src
        if not src.startswith('['):
            raise self.ParseError('Selector Attribute opening \'[\' not found', src, ctxsrc)
        src = src[1:].lstrip()

        nsPrefix, src = self._get_match_result(self.re_namespace_selector, src)
        attrName, src = self._get_ident(src)

        src = src.lstrip()

        if attrName is None:
            raise self.ParseError('Expected a selector attribute name', src, ctxsrc)
        if nsPrefix is not None:
            attrName = self.css_builder.resolve_namespace_prefix(nsPrefix, attrName)

        for op in self.attribute_operators:
            if src.startswith(op):
                break
        else:
            op = ''
        src = src[len(op):].lstrip()

        if op:
            attrValue, src = self._get_ident(src)
            if attrValue is None:
                attrValue, src = self._get_string(src)
                if attrValue is None:
                    raise self.ParseError('Expected a selector attribute value', src, ctxsrc)
        else:
            attrValue = None

        if not src.startswith(']'):
            raise self.ParseError('Selector Attribute closing \']\' not found', src, ctxsrc)
        else:
            src = src[1:]

        if op:
            selector.add_attribute_operation(attrName, op, attrValue)
        else:
            selector.add_attribute(attrName)
        return src, selector

    def _parse_selector_pseudo(self, src, selector):
        """pseudo
        : ':' [ IDENT | function ]
        ;
        """
        ctxsrc = src
        if not src.startswith(':'):
            raise self.ParseError('Selector Pseudo \':\' not found', src, ctxsrc)
        src = re.search('^:{1,2}(.*)', src, re.M | re.S).group(1)

        name, src = self._get_ident(src)
        if not name:
            raise self.ParseError('Selector Pseudo identifier not found', src, ctxsrc)

        if src.startswith('('):
            # function
            src = src[1:].lstrip()
            src, term = self._parse_expression(src, True)
            if not src.startswith(')'):
                raise self.ParseError('Selector Pseudo Function closing \')\' not found', src, ctxsrc)
            src = src[1:]
            selector.add_pseudo_function(name, term)
        else:
            selector.add_pseudo(name)

        return src, selector

    # ~ declaration and expression parsing ~~~~~~~~~~~~~~~

    def _parse_declaration_group(self, src, braces=True):
        ctxsrc = src
        if src.startswith('{'):
            src, braces = src[1:], True
        elif braces:
            raise self.ParseError('Declaration group opening \'{\' not found', src, ctxsrc)

        properties = []
        src = src.lstrip()
        while src[:1] not in ('', ',', '{', '}', '[', ']', '(', ')', '@'): # XXX @?
            src, property = self._parse_declaration(src)

            # XXX Workaround for styles like "*font: smaller"
            if src.startswith("*"):
                src = "-nothing-" + src[1:]
                continue

            if property is None:
                break
            properties.append(property)
            if src.startswith(';'):
                src = src[1:].lstrip()
            else:
                break

        if braces:
            if not src.startswith('}'):
                raise self.ParseError('Declaration group closing \'}\' not found', src, ctxsrc)
            src = src[1:]

        return src.lstrip(), properties

    def _parse_declaration(self, src):
        """declaration
        : ident S* ':' S* expr prio?
        | /* empty */
        ;
        """
        # property
        property_name, src = self._get_ident(src)

        if property_name is not None:
            src = src.lstrip()
            # S* : S*
            if src[:1] in (':', '='):
                # Note: we are being fairly flexable here...  technically, the
                # ":" is *required*, but in the name of flexibility we
                # suppor a null transition, as well as an "=" transition
                src = src[1:].lstrip()

            src, property = self._parse_declaration_property(src, property_name)
        else:
            property = None

        return src, property

    def _parse_declaration_property(self, src, propertyName):
        # expr
        src, expr = self._parse_expression(src)

        # prio?
        important, src = self._get_match_result(self.re_important, src)
        src = src.lstrip()

        property = self.css_builder.property(propertyName, expr, important)
        return src, property

    def _parse_expression(self, src, returnList=False):
        """
        expr
        : term [ operator term ]*
        ;
        """
        src, term = self._parse_expression_term(src)
        operator = None
        while src[:1] not in ('', ';', '{', '}', '[', ']', ')'):
            for operator in self.expression_operators:
                if src.startswith(operator):
                    src = src[len(operator):]
                    break
            else:
                operator = ' '
            src, term2 = self._parse_expression_term(src.lstrip())
            if term2 is NotImplemented:
                break
            else:
                term = self.css_builder.combine_terms(term, operator, term2)

        if operator is None and returnList:
            term = self.css_builder.combine_terms(term, None, None)
            return src, term
        else:
            return src, term

    def _parse_expression_term(self, src):
        """term
        : unary_operator?
            [ NUMBER S* | PERCENTAGE S* | LENGTH S* | EMS S* | EXS S* | ANGLE S* |
            TIME S* | FREQ S* | function ]
        | STRING S* | IDENT S* | URI S* | RGB S* | UNICODERANGE S* | hexcolor
        ;
        """
        ctxsrc = src

        result, src = self._get_match_result(self.re_num, src)
        if result is not None:
            units, src = self._get_match_result(self.re_unit, src)
            term = self.css_builder.term_number(result, units)
            return src.lstrip(), term

        result, src = self._get_string(src, self.re_uri)
        if result is not None:
            # XXX URL!!!!
            term = self.css_builder.term_uri(result)
            return src.lstrip(), term

        result, src = self._get_string(src)
        if result is not None:
            term = self.css_builder.term_string(result)
            return src.lstrip(), term

        result, src = self._get_match_result(self.re_functionterm, src)
        if result is not None:
            src, params = self._parse_expression(src, True)
            if src[0] != ')':
                raise self.ParseError('Terminal function expression expected closing \')\'', src, ctxsrc)
            src = src[1:].lstrip()
            term = self.css_builder.term_function(result, params)
            return src, term

        result, src = self._get_match_result(self.re_rgbcolor, src)
        if result is not None:
            term = self.css_builder.term_rgb(result)
            return src.lstrip(), term

        result, src = self._get_match_result(self.re_unicoderange, src)
        if result is not None:
            term = self.css_builder.term_unicode_range(result)
            return src.lstrip(), term

        nsPrefix, src = self._get_match_result(self.re_namespace_selector, src)
        result, src = self._get_ident(src)
        if result is not None:
            if nsPrefix is not None:
                result = self.css_builder.resolve_namespace_prefix(nsPrefix, result)
            term = self.css_builder.term_ident(result)
            return src.lstrip(), term

        result, src = self._get_match_result(self.re_unicodeid, src)
        if result is not None:
            term = self.css_builder.term_ident(result)
            return src.lstrip(), term

        return self.css_builder.term_unknown(src)

    # ~ utility methods ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _get_ident(self, src, default=None):
        return self._get_match_result(self.re_ident, src, default)

    def _get_string(self, src, rexpression=None, default=None):
        if rexpression is None:
            rexpression = self.re_string
        result = rexpression.match(src)
        if result:
            strres = filter(None, result.groups())
            if strres:
                try:
                    strres = strres[0]
                except Exception:
                    strres = result.groups()[0]
            else:
                strres = ''
            return strres, src[result.end():]
        else:
            return default, src

    def _get_string_or_uri(self, src):
        result, src = self._get_string(src, self.re_uri)
        if result is None:
            result, src = self._get_string(src)
        return result, src

    def _get_match_result(self, rexpression, src, default=None, group=1):
        result = rexpression.match(src)
        if result:
            return result.group(group), src[result.end():]
        else:
            return default, src

