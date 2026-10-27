ObjC.import('Cocoa');
ObjC.import('Foundation');

function colorFromHex(hex, alpha) {
  if (alpha === undefined) alpha = 1.0;
  var clean = hex.replace('#', '');
  var r = parseInt(clean.substring(0, 2), 16) / 255.0;
  var g = parseInt(clean.substring(2, 4), 16) / 255.0;
  var b = parseInt(clean.substring(4, 6), 16) / 255.0;
  return $.NSColor.colorWithSRGBRedGreenBlueAlpha(r, g, b, alpha);
}

function getFont(name, size) {
  var font = $.NSFont.fontWithNameSize(name, size);
  if (!font || font.isNil()) {
    font = $.NSFont.boldSystemFontOfSize(size);
  }
  return font;
}

function makeAttrs(font, color, lineSpacing) {
  var style = $.NSMutableParagraphStyle.alloc.init;
  style.setLineSpacing(lineSpacing || 10);
  var attrs = $.NSMutableDictionary.alloc.init;
  attrs.setObjectForKey(font, $.NSFontAttributeName);
  attrs.setObjectForKey(color, $.NSForegroundColorAttributeName);
  attrs.setObjectForKey(style, $.NSParagraphStyleAttributeName);
  return attrs;
}

function measureWidth(str, attrs) {
  var ns = $.NSString.stringWithString(String(str));
  return ns.sizeWithAttributes(attrs).width;
}

function measureHeight(str, attrs) {
  var ns = $.NSString.stringWithString(String(str));
  return ns.sizeWithAttributes(attrs).height;
}

function tokenizeForWrap(str) {
  return String(str || '').match(/([（(][A-Za-z0-9\-\/+]{1,10}[）)]|[A-Za-z0-9\-\/.+%]+|.[，。、；：！？）》」』\]\)]?)/g) || [];
}

function wrapLines(text, maxWidth, attrs) {
  var paragraphs = String(text || '').split('\n');
  var lines = [];
  for (var p = 0; p < paragraphs.length; p++) {
    var tokens = tokenizeForWrap(paragraphs[p]);
    var line = '';
    for (var i = 0; i < tokens.length; i++) {
      var testLine = line + tokens[i];
      if (measureWidth(testLine, attrs) > maxWidth && line.length > 0) {
        lines.push(line);
        line = tokens[i];
      } else {
        line = testLine;
      }
    }
    if (line.length > 0 || paragraphs.length > 1) {
      lines.push(line);
    }
  }
  return lines;
}

function drawWrappedBoxText(text, boxX, boxY, boxW, boxH, padX, fontName, baseSize, color, lineGap, align) {
  var maxW = boxW - padX * 2;
  var fontSize = baseSize;
  var font, attrs, lines, singleH, totalH;
  var gap = (lineGap !== undefined) ? lineGap : 10;

  while (fontSize >= 18) {
    font = getFont(fontName, fontSize);
    attrs = makeAttrs(font, color, gap);
    lines = wrapLines(text, maxW, attrs);
    singleH = measureHeight('測試Ag', attrs);
    totalH = lines.length * singleH + Math.max(0, lines.length - 1) * gap;
    if (totalH <= boxH - 20) break;
    fontSize -= 2;
  }

  // In AppKit lockFocus, Y=0 is at the bottom, so top line has the highest Y
  var curY = boxY + (boxH + totalH) / 2.0 - singleH;
  for (var i = 0; i < lines.length; i++) {
    var ln = lines[i];
    var ns = $.NSString.stringWithString(ln);
    var lw = ns.sizeWithAttributes(attrs).width;
    var drawX = (align === 'center') ? (boxX + (boxW - lw) / 2.0) : (boxX + padX);
    ns.drawAtPointWithAttributes($.NSMakePoint(drawX, curY), attrs);
    curY -= (singleH + gap);
  }
}

function drawText(text, x, y, width, height, font, color, lineSpacing, align) {
  var attrs = makeAttrs(font, color, lineSpacing);
  var nsStr = $.NSString.stringWithString(String(text));
  if (align === 'center') {
    var sz = nsStr.sizeWithAttributes(attrs);
    var drawX = x + (width - sz.width) / 2.0;
    var drawY = y + (height - sz.height) / 2.0;
    nsStr.drawAtPointWithAttributes($.NSMakePoint(drawX, drawY), attrs);
  } else {
    nsStr.drawInRectWithAttributes($.NSMakeRect(x, y, width, height), attrs);
  }
}

function drawRoundedRect(x, y, w, h, radius, fillColor, strokeColor, lineWidth) {
  var path = $.NSBezierPath.bezierPathWithRoundedRectXRadiusYRadius($.NSMakeRect(x, y, w, h), radius, radius);
  if (fillColor) {
    fillColor.setFill;
    path.fill;
  }
  if (strokeColor) {
    strokeColor.setStroke;
    path.setLineWidth(lineWidth || 2.0);
    path.stroke;
  }
}

function renderSlide(post, slide, totalSlides, outPath) {
  var W = 1080;
  var H = 1350;

  var img = $.NSImage.alloc.initWithSize($.NSMakeSize(W, H));
  img.lockFocus;

  var themeColor = colorFromHex(post.theme_color, 1.0);
  var accentColor = colorFromHex(post.accent_color, 1.0);
  var darkBg = colorFromHex('#0F172A', 1.0);
  var white = colorFromHex('#FFFFFF', 1.0);
  var offWhite = colorFromHex('#F8FAFC', 1.0);
  var slateDark = colorFromHex('#1E293B', 1.0);
  var slateBody = colorFromHex('#334155', 1.0);

  // Clean solid dark base + layered translucent theme panels
  drawRoundedRect(0, 0, W, H, 0, darkBg, null);
  drawRoundedRect(0, 0, W, H, 0, colorFromHex(post.theme_color, 0.42), null);
  drawRoundedRect(-180, 520, 980, 980, 490, colorFromHex(post.theme_color, 0.35), null);

  // Decorative background circles
  drawRoundedRect(760, 980, 420, 420, 210, colorFromHex(post.accent_color, 0.16), null);
  drawRoundedRect(-120, -100, 380, 380, 190, colorFromHex('#FFFFFF', 0.06), null);

  var fontHeavy68 = getFont('PingFangTC-Semibold', 58);
  var fontBold54 = getFont('PingFangTC-Semibold', 48);
  var fontSemi36 = getFont('PingFangTC-Semibold', 33);
  var fontReg28 = getFont('PingFangTC-Regular', 25);
  var fontBold26 = getFont('PingFangTC-Semibold', 25);

  // Category pill on top left (auto-width)
  var catAttrs = makeAttrs(fontBold26, white, 4);
  var catW = Math.max(260, Math.ceil(measureWidth(post.category, catAttrs)) + 64);
  drawRoundedRect(80, 1195, catW, 62, 31, colorFromHex('#FFFFFF', 0.16), colorFromHex('#FFFFFF', 0.35), 1.5);
  drawText(post.category, 80, 1195, catW, 62, fontBold26, white, 4, 'center');

  // Slide counter pill on top right
  drawRoundedRect(860, 1195, 140, 62, 31, colorFromHex('#000000', 0.28), null);
  drawText(slide.slide_num + ' / ' + totalSlides, 860, 1195, 140, 62, fontBold26, white, 4, 'center');

  if (slide.type === 'cover') {
    drawRoundedRect(75, 200, 930, 930, 42, colorFromHex('#0F172A', 0.55), colorFromHex('#FFFFFF', 0.22), 2.0);
    var tagStr = '✦ ' + slide.tag;
    var tagW = Math.max(310, Math.ceil(measureWidth(tagStr, catAttrs)) + 64);
    drawRoundedRect(135, 975, tagW, 66, 16, accentColor, null);
    drawText(tagStr, 135, 975, tagW, 66, fontBold26, white, 4, 'center');

    drawText(slide.headline, 135, 535, 810, 390, fontHeavy68, white, 18, 'left');
    drawRoundedRect(135, 505, 160, 8, 4, accentColor, null);
    drawText(slide.subheadline, 135, 340, 810, 135, fontSemi36, colorFromHex('#E2E8F0', 0.95), 12, 'left');

    var metaText = slide.meta_badge || ('研究機構：' + post.source_name);
    drawRoundedRect(135, 245, 810, 74, 37, colorFromHex('#FFFFFF', 0.12), null);
    drawWrappedBoxText(metaText, 135, 245, 810, 74, 30, 'PingFangTC-Semibold', 25, white, 6, 'center');

  } else if (slide.type === 'points') {
    drawRoundedRect(75, 200, 930, 940, 42, offWhite, null);
    var pTagW = Math.max(230, Math.ceil(measureWidth(slide.tag, catAttrs)) + 60);
    drawRoundedRect(135, 1005, pTagW, 60, 14, themeColor, null);
    drawText(slide.tag, 135, 1005, pTagW, 60, fontBold26, white, 4, 'center');
    drawText(slide.headline, 135, 800, 810, 175, fontBold54, slateDark, 14, 'left');

    var pts = slide.points || [];
    for (var i = 0; i < pts.length; i++) {
      var boxY = 610 - i * 180;
      drawRoundedRect(130, boxY, 820, 156, 24, white, colorFromHex(post.theme_color, 0.22), 2.0);
      drawRoundedRect(158, boxY + 44, 68, 68, 34, themeColor, null);
      drawText('0' + (i + 1), 158, boxY + 44, 68, 68, fontSemi36, white, 2, 'center');
      drawWrappedBoxText(pts[i], 246, boxY, 680, 156, 16, 'PingFangTC-Medium', 29, slateBody, 8, 'left');
    }

  } else if (slide.type === 'takeaway') {
    drawRoundedRect(75, 200, 930, 940, 42, offWhite, null);
    var tTagW = Math.max(240, Math.ceil(measureWidth(slide.tag, catAttrs)) + 60);
    drawRoundedRect(135, 1005, tTagW, 60, 14, accentColor, null);
    drawText(slide.tag, 135, 1005, tTagW, 60, fontBold26, white, 4, 'center');
    drawText(slide.headline, 135, 790, 810, 185, fontBold54, slateDark, 14, 'left');

    drawRoundedRect(130, 425, 820, 340, 28, colorFromHex(post.theme_color, 0.09), themeColor, 2.5);
    drawText('■ 學術與臨床意義', 175, 685, 730, 50, fontSemi36, themeColor, 6, 'left');
    drawWrappedBoxText(slide.summary, 130, 435, 820, 245, 45, 'PingFangTC-Medium', 30, slateDark, 10, 'left');

    // Bottom CTA pill box with automatic multi-line wrapping & centering
    drawRoundedRect(130, 245, 820, 145, 26, themeColor, null);
    drawWrappedBoxText(slide.cta, 130, 245, 820, 145, 42, 'PingFangTC-Medium', 26, white, 8, 'center');
  }

  var footerText = slide.footer || ('資料來源：' + post.source_name);
  drawText(footerText, 85, 95, 720, 45, fontReg28, colorFromHex('#E2E8F0', 0.85), 4, 'left');

  for (var d = 1; d <= totalSlides; d++) {
    var dotW = (d === slide.slide_num) ? 44 : 16;
    var dotX = 830 + (d - 1) * 32 + (d > slide.slide_num ? 28 : 0);
    var dotColor = (d === slide.slide_num) ? accentColor : colorFromHex('#FFFFFF', 0.35);
    drawRoundedRect(dotX, 112, dotW, 16, 8, dotColor, null);
  }

  img.unlockFocus;

  var tiff = img.TIFFRepresentation;
  var rep = $.NSBitmapImageRep.imageRepWithData(tiff);
  var pngData = rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $.NSDictionary.dictionary);
  pngData.writeToFileAtomically(outPath, true);
}

function run(argv) {
  var jsonPath = argv[0];
  var outDir = argv[1];
  var jsonStr = $.NSString.stringWithContentsOfFileEncodingError(jsonPath, $.NSUTF8StringEncoding, null).js;
  var data = JSON.parse(jsonStr);

  var fm = $.NSFileManager.defaultManager;
  fm.createDirectoryAtPathWithIntermediateDirectoriesAttributesError(outDir, true, $(), $());

  var count = 0;
  for (var i = 0; i < data.posts.length; i++) {
    var post = data.posts[i];
    var slides = post.slides;
    for (var s = 0; s < slides.length; s++) {
      var fileName = post.id + '_slide_' + slides[s].slide_num + '.png';
      var outPath = outDir + '/' + fileName;
      renderSlide(post, slides[s], slides.length, outPath);
      count++;
    }
  }
  return 'Rendered ' + count + ' slides to ' + outDir;
}
