/**************************************************************
 * KIỂM KÊ CCDC — theo từng cửa hàng (sheet)
 * File: Mẫu CCDC
 * https://docs.google.com/spreadsheets/d/13C9m7WaQA_wD0tdeQEuMj3EzncBksjEPEcKVio57u-s
 *
 * Mỗi cửa hàng = 1 sheet (AEHP, AEHD, LUG_KDV, ...)
 * Header dòng 6, dữ liệu từ dòng 7:
 * A Mã | B Tên | C SL | D ĐVT | E Kích thước | F Chất liệu
 * G Màu sắc | H Tình trạng | I Hình ảnh | J Ghi chú
 **************************************************************/

const CONFIG = {
  SPREADSHEET_ID: '13C9m7WaQA_wD0tdeQEuMj3EzncBksjEPEcKVio57u-s',

  // Sheet không phải cửa hàng
  EXCLUDE_SHEETS: ['timeline', 'test', 'Test', 'CH', 'TỔNG', 'DanhMucVatTu'],

  DRIVE_FOLDER_ID: '',
  IMAGE_FOLDER_NAME: 'KiemKe_CCDC_Images',
  IMAGE_ROW_HEIGHT: 160,
  IMAGE_COL_WIDTH: 200,

  HEADER_ROW: 6,
  DATA_START_ROW: 7,

  COL: {
    MA: 1,
    TEN: 2,
    SL: 3,
    DVT: 4,
    KICH_THUOC: 5,
    CHAT_LIEU: 6,
    MAU_SAC: 7,
    TINH_TRANG: 8,
    HINH_ANH: 9,
    GHI_CHU: 10
  }
};

function doGet(e) {
  // API cho app mobile: ?action=cuaHang | vatTu&cuaHang=AEHP
  var action = e && e.parameter && e.parameter.action;
  if (action) {
    return apiGet_(action, e.parameter || {});
  }

  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Kiểm kê CCDC')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1, maximum-scale=1');
}

function doPost(e) {
  try {
    var body = {};
    if (e && e.postData && e.postData.contents) {
      body = JSON.parse(e.postData.contents);
    }
    if (body.action === 'save') {
      return jsonOut_(saveKiemKe(body.payload || body));
    }
    return jsonOut_({ ok: false, message: 'action không hợp lệ' });
  } catch (err) {
    return jsonOut_({ ok: false, message: String(err.message || err) });
  }
}

function apiGet_(action, params) {
  try {
    if (action === 'cuaHang' || action === 'stores') {
      return jsonOut_({ ok: true, data: getCuaHangList() });
    }
    if (action === 'vatTu' || action === 'items') {
      var cuaHang = params.cuaHang || params.store || '';
      return jsonOut_({ ok: true, data: getVatTuList(cuaHang) });
    }
    return jsonOut_({ ok: false, message: 'action không hợp lệ: ' + action });
  } catch (err) {
    return jsonOut_({ ok: false, message: String(err.message || err) });
  }
}

function jsonOut_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function getSpreadsheet_() {
  return SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID);
}

function getStoreSheet_(cuaHang) {
  const name = String(cuaHang || '').trim();
  if (!name) throw new Error('Thiếu tên cửa hàng.');
  const sheet = getSpreadsheet_().getSheetByName(name);
  if (!sheet) throw new Error('Không tìm thấy sheet cửa hàng: ' + name);
  return sheet;
}

/** Danh sách cửa hàng = tên các sheet (trừ sheet hệ thống) */
function getCuaHangList() {
  const exclude = {};
  (CONFIG.EXCLUDE_SHEETS || []).forEach(function (n) {
    exclude[String(n).toLowerCase()] = true;
  });

  return getSpreadsheet_()
    .getSheets()
    .map(function (s) { return s.getName(); })
    .filter(function (name) {
      return name && !exclude[String(name).toLowerCase()];
    })
    .sort(function (a, b) {
      return a.localeCompare(b, 'vi');
    });
}

/**
 * Vật tư theo đúng sheet cửa hàng.
 * @param {string} cuaHang tên sheet, ví dụ "AEHP"
 */
function getVatTuList(cuaHang) {
  const sheet = getStoreSheet_(cuaHang);
  const lastRow = sheet.getLastRow();
  if (lastRow < CONFIG.DATA_START_ROW) return [];

  const values = sheet
    .getRange(CONFIG.DATA_START_ROW, 1, lastRow, CONFIG.COL.GHI_CHU)
    .getValues();

  const list = [];
  values.forEach(function (row, i) {
    const ma = String(row[CONFIG.COL.MA - 1] || '').trim();
    const ten = String(row[CONFIG.COL.TEN - 1] || '').trim();
    // Cho phép dòng có tên nhưng chưa có mã (theo hướng dẫn trên sheet)
    if (!ma && !ten) return;

    list.push({
      row: CONFIG.DATA_START_ROW + i,
      ma: ma,
      ten: ten,
      sl: row[CONFIG.COL.SL - 1] !== '' && row[CONFIG.COL.SL - 1] != null
        ? row[CONFIG.COL.SL - 1]
        : '',
      dvt: String(row[CONFIG.COL.DVT - 1] || '').trim(),
      kichThuoc: String(row[CONFIG.COL.KICH_THUOC - 1] || '').trim(),
      chatLieu: String(row[CONFIG.COL.CHAT_LIEU - 1] || '').trim(),
      mauSac: String(row[CONFIG.COL.MAU_SAC - 1] || '').trim(),
      tinhTrang: String(row[CONFIG.COL.TINH_TRANG - 1] || '').trim(),
      ghiChu: String(row[CONFIG.COL.GHI_CHU - 1] || '').trim()
    });
  });

  return list;
}

/**
 * payload = {
 *   cuaHang, ma, ten, sl, dvt, kichThuoc, chatLieu, mauSac, tinhTrang, ghiChu,
 *   imageBase64, imageMimeType, imageName
 * }
 */
function saveKiemKe(payload) {
  try {
    if (!payload || !payload.cuaHang) {
      return { ok: false, message: 'Thiếu cửa hàng.' };
    }
    if (!payload.ma && !payload.ten) {
      return { ok: false, message: 'Thiếu mã hoặc tên vật tư.' };
    }

    const sheet = getStoreSheet_(payload.cuaHang);
    let row = null;

    if (payload.ma) {
      row = findRowByMa_(sheet, payload.ma);
    }
    if (!row && payload.ten) {
      row = findRowByTen_(sheet, payload.ten);
    }
    if (!row) {
      return {
        ok: false,
        message:
          'Không tìm thấy vật tư trên sheet "' +
          payload.cuaHang +
          '".'
      };
    }

    const c = CONFIG.COL;
    if (payload.ten) sheet.getRange(row, c.TEN).setValue(payload.ten);
    sheet.getRange(row, c.SL).setValue(
      payload.sl !== '' && payload.sl != null ? Number(payload.sl) : ''
    );
    sheet.getRange(row, c.DVT).setValue(payload.dvt || '');
    sheet.getRange(row, c.KICH_THUOC).setValue(payload.kichThuoc || '');
    sheet.getRange(row, c.CHAT_LIEU).setValue(payload.chatLieu || '');
    sheet.getRange(row, c.MAU_SAC).setValue(payload.mauSac || '');
    sheet.getRange(row, c.TINH_TRANG).setValue(payload.tinhTrang || '');
    sheet.getRange(row, c.GHI_CHU).setValue(payload.ghiChu || '');

    if (payload.imageBase64) {
      setInCellImage_(sheet, row, c.HINH_ANH, payload);
    }

    SpreadsheetApp.flush();
    return {
      ok: true,
      message:
        'Đã lưu ' +
        payload.cuaHang +
        ' — dòng ' +
        row +
        (payload.ma ? ' — mã ' + payload.ma : ''),
      row: row,
      cuaHang: payload.cuaHang
    };
  } catch (err) {
    return { ok: false, message: String(err.message || err) };
  }
}

function findRowByMa_(sheet, ma) {
  const lastRow = sheet.getLastRow();
  if (lastRow < CONFIG.DATA_START_ROW) return null;

  const values = sheet
    .getRange(CONFIG.DATA_START_ROW, CONFIG.COL.MA, lastRow, CONFIG.COL.MA)
    .getValues();
  const target = String(ma).trim().toUpperCase();

  for (let i = 0; i < values.length; i++) {
    if (String(values[i][0] || '').trim().toUpperCase() === target) {
      return CONFIG.DATA_START_ROW + i;
    }
  }
  return null;
}

function findRowByTen_(sheet, ten) {
  const lastRow = sheet.getLastRow();
  if (lastRow < CONFIG.DATA_START_ROW) return null;

  const values = sheet
    .getRange(CONFIG.DATA_START_ROW, CONFIG.COL.TEN, lastRow, CONFIG.COL.TEN)
    .getValues();
  const target = String(ten).trim().toUpperCase();

  for (let i = 0; i < values.length; i++) {
    if (String(values[i][0] || '').trim().toUpperCase() === target) {
      return CONFIG.DATA_START_ROW + i;
    }
  }
  return null;
}

function getImageFolder_() {
  const props = PropertiesService.getScriptProperties();
  const configured = String(CONFIG.DRIVE_FOLDER_ID || '').trim();

  if (configured && configured !== 'THAY_FOLDER_ID_CUA_BAN') {
    return DriveApp.getFolderById(configured);
  }

  const cachedId = props.getProperty('IMAGE_FOLDER_ID');
  if (cachedId) {
    try {
      return DriveApp.getFolderById(cachedId);
    } catch (e) {
      // tạo lại
    }
  }

  const folderName = CONFIG.IMAGE_FOLDER_NAME || 'KiemKe_CCDC_Images';
  const existing = DriveApp.getFoldersByName(folderName);
  const folder = existing.hasNext() ? existing.next() : DriveApp.createFolder(folderName);
  props.setProperty('IMAGE_FOLDER_ID', folder.getId());
  return folder;
}

function setInCellImage_(sheet, row, col, payload) {
  const folder = getImageFolder_();
  const mime = payload.imageMimeType || 'image/jpeg';
  const name =
    (payload.cuaHang || '') +
    '_' +
    (payload.imageName || payload.ma || payload.ten || 'anh') +
    '_' +
    Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyyMMdd_HHmmss');

  const raw = String(payload.imageBase64).replace(/^data:[^;]+;base64,/, '');
  const blob = Utilities.newBlob(Utilities.base64Decode(raw), mime, name);
  const file = folder.createFile(blob);

  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  const url = 'https://drive.google.com/uc?export=view&id=' + file.getId();

  sheet.setColumnWidth(col, CONFIG.IMAGE_COL_WIDTH || 200);
  sheet.setRowHeight(row, CONFIG.IMAGE_ROW_HEIGHT || 160);
  sheet.getRange(row, col).setFormula('=IMAGE("' + url + '")');
}
