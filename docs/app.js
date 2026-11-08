(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) {
    module.exports = factory();
  } else {
    root.PsyCourseApp = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const COURSE_FIELD_NAMES = [
    "課程名稱",
    "主辦單位",
    "課程日期",
    "上課時間",
    "費用",
    "上課地點／方式",
    "報名連結",
    "是否有臨床心理師積分",
    "積分判斷依據段落",
    "資料來源平台",
    "建立時間",
    "報名期間",
  ];

  function escapeHtml(value) {
    const str = value == null ? "" : String(value);
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function extractCourseMonth(courseDate) {
    if (!courseDate) {
      return "";
    }
    const match = String(courseDate).trim().match(/^(\d{2,4}\/\d{2})/);
    return match ? match[1] : "";
  }

  function matchesModeFilter(course, modeFilter) {
    if (!modeFilter) {
      return true;
    }
    const loc = String(course["上課地點／方式"] || "");
    const title = String(course["課程名稱"] || "");
    const combined = loc + " " + title;
    const onlinePattern = /線上|視訊|網路|直播|zoom|google\s*meet|webex|teams/i;
    const physicalPattern = /實體|現場|混合|館|院|樓|室|中心|大學|學會|教室|市|縣|區|路|街|號/;

    if (modeFilter === "線上") {
      return onlinePattern.test(combined);
    }
    if (modeFilter === "實體") {
      if (physicalPattern.test(combined)) {
        return true;
      }
      return Boolean(loc.trim()) && !onlinePattern.test(loc);
    }
    return true;
  }

  function matchesFeeFilter(course, feeFilter) {
    if (!feeFilter) {
      return true;
    }
    const fee = String(course["費用"] || "").trim();
    const isFree = /免費|免收|0\s*元|\$0\b/.test(fee);
    if (feeFilter === "免費") {
      return isFree;
    }
    if (feeFilter === "付費") {
      return Boolean(fee) && !isFree;
    }
    return true;
  }

  function filterCourses(courses, filters) {
    const active = filters || {};
    const keyword = String(active.keyword || "").trim().toLowerCase();
    const credit = String(active.credit || "").trim();
    const mode = String(active.mode || "").trim();
    const fee = String(active.fee || "").trim();
    const month = String(active.month || "").trim();
    const source = String(active.source || "").trim();

    return (courses || []).filter(function (course) {
      if (credit && String(course["是否有臨床心理師積分"] || "") !== credit) {
        return false;
      }
      if (month && extractCourseMonth(course["課程日期"]) !== month) {
        return false;
      }
      if (source && String(course["資料來源平台"] || "") !== source) {
        return false;
      }
      if (!matchesModeFilter(course, mode)) {
        return false;
      }
      if (!matchesFeeFilter(course, fee)) {
        return false;
      }
      if (keyword) {
        const haystack = [
          course["課程名稱"],
          course["主辦單位"],
          course["上課地點／方式"],
          course["積分判斷依據段落"],
          course["資料來源平台"],
          course["課程日期"],
        ]
          .map(function (v) {
            return String(v || "").toLowerCase();
          })
          .join(" ");
        if (!haystack.includes(keyword)) {
          return false;
        }
      }
      return true;
    });
  }

  function buildImportDataFormula(locationHref) {
    try {
      const csvUrl = new URL("./data/courses.csv", locationHref).href;
      return '=IMPORTDATA("' + csvUrl + '")';
    } catch (_err) {
      return '=IMPORTDATA("./data/courses.csv")';
    }
  }

  function escapeCsvCell(value) {
    const str = value == null ? "" : String(value);
    if (/[",\r\n]/.test(str)) {
      return '"' + str.replace(/"/g, '""') + '"';
    }
    return str;
  }

  function coursesToCsvWithBom(courses) {
    const lines = [COURSE_FIELD_NAMES.map(escapeCsvCell).join(",")];
    (courses || []).forEach(function (course) {
      const row = COURSE_FIELD_NAMES.map(function (field) {
        return escapeCsvCell(course[field] || "");
      });
      lines.push(row.join(","));
    });
    return "\uFEFF" + lines.join("\r\n") + "\r\n";
  }

  function getBadgeClass(creditStatus) {
    if (creditStatus === "是") {
      return "badge badge-yes";
    }
    if (creditStatus === "否") {
      return "badge badge-no";
    }
    return "badge badge-unknown";
  }

  function renderEvidenceCell(evidenceText) {
    const text = String(evidenceText || "").trim() || "未提供";
    const escapedFull = escapeHtml(text);
    const preview = text.length > 26 ? escapeHtml(text.slice(0, 26) + "…") : escapedFull;
    return (
      '<details class="evidence-details">' +
      "<summary>" +
      preview +
      "</summary>" +
      '<div class="evidence-full">' +
      escapedFull +
      "</div>" +
      "</details>"
    );
  }

  function renderRegistrationLink(url) {
    const raw = String(url || "").trim();
    if (!/^https?:\/\//i.test(raw)) {
      return "-";
    }
    return (
      '<a class="link-btn" href="' +
      escapeHtml(raw) +
      '" target="_blank" rel="noopener noreferrer">前往報名／公告 ↗</a>'
    );
  }

  function initBrowserApp() {
    if (typeof document === "undefined") {
      return;
    }
    const tableEl = document.getElementById("courses-table");
    const tbodyEl = document.getElementById("courses-tbody");
    if (!tableEl || !tbodyEl) {
      return;
    }

    const keywordInput = document.getElementById("filter-keyword");
    const creditSelect = document.getElementById("filter-credit");
    const modeSelect = document.getElementById("filter-mode");
    const feeSelect = document.getElementById("filter-fee");
    const monthSelect = document.getElementById("filter-month");
    const sourceSelect = document.getElementById("filter-source");
    const resetBtn = document.getElementById("btn-reset-filters");

    const countEl = document.getElementById("course-count");
    const updatedEl = document.getElementById("last-updated");
    const sourceSummaryEl = document.getElementById("source-status-summary");
    const downloadCsvBtn = document.getElementById("btn-download-csv");
    const exportFilteredBtn = document.getElementById("btn-export-filtered-csv");
    const sheetsSyncBtn = document.getElementById("btn-sheets-sync");

    const modalEl = document.getElementById("sheets-modal");
    const closeModalBtn = document.getElementById("btn-close-modal");
    const formulaInput = document.getElementById("sheets-formula-input");
    const copyFormulaBtn = document.getElementById("btn-copy-formula");
    const copyFeedbackEl = document.getElementById("copy-feedback");

    let allCourses = [];
    let currentFiltered = [];

    if (formulaInput && typeof window !== "undefined" && window.location) {
      formulaInput.value = buildImportDataFormula(window.location.href);
    }

    if (downloadCsvBtn) {
      downloadCsvBtn.setAttribute("href", "./data/courses.csv");
    }

    function getActiveFilters() {
      return {
        keyword: keywordInput ? keywordInput.value : "",
        credit: creditSelect ? creditSelect.value : "",
        mode: modeSelect ? modeSelect.value : "",
        fee: feeSelect ? feeSelect.value : "",
        month: monthSelect ? monthSelect.value : "",
        source: sourceSelect ? sourceSelect.value : "",
      };
    }

    function renderRows(courses) {
      if (!courses.length) {
        tbodyEl.innerHTML =
          '<tr><td colspan="11" class="empty-cell">沒有符合目前篩選條件的課程，請調整篩選條件後再試。</td></tr>';
        return;
      }

      const htmlRows = courses.map(function (course) {
        const creditStatus = String(course["是否有臨床心理師積分"] || "未知");
        const badgeClass = getBadgeClass(creditStatus);
        return (
          "<tr>" +
          '<td class="course-name-cell" data-label="課程名稱">' +
          escapeHtml(course["課程名稱"] || "") +
          "</td>" +
          '<td data-label="主辦單位">' +
          escapeHtml(course["主辦單位"] || "") +
          "</td>" +
          '<td class="date-cell" data-label="課程日期">' +
          escapeHtml(course["課程日期"] || "") +
          "</td>" +
          '<td class="time-cell" data-label="上課時間">' +
          escapeHtml(course["上課時間"] || "") +
          "</td>" +
          '<td class="reg-period-cell" data-label="報名期間">' +
          escapeHtml(course["報名期間"] || "") +
          "</td>" +
          '<td data-label="費用">' +
          escapeHtml(course["費用"] || "") +
          "</td>" +
          '<td data-label="上課地點／方式">' +
          escapeHtml(course["上課地點／方式"] || "") +
          "</td>" +
          '<td data-label="報名連結">' +
          renderRegistrationLink(course["報名連結"]) +
          "</td>" +
          '<td data-label="是否有臨床心理師積分"><span class="' +
          badgeClass +
          '">' +
          escapeHtml(creditStatus) +
          "</span></td>" +
          '<td data-label="積分判斷依據段落">' +
          renderEvidenceCell(course["積分判斷依據段落"]) +
          "</td>" +
          '<td data-label="資料來源平台">' +
          escapeHtml(course["資料來源平台"] || "") +
          "</td>" +
          "</tr>"
        );
      });

      tbodyEl.innerHTML = htmlRows.join("");
    }

    function applyFiltersAndRender() {
      currentFiltered = filterCourses(allCourses, getActiveFilters());
      if (countEl) {
        countEl.textContent =
          "顯示 " + currentFiltered.length + " / 共 " + allCourses.length + " 筆課程";
      }
      renderRows(currentFiltered);
    }

    function populateDynamicSelects(courses) {
      const monthsSet = new Set();
      const sourcesSet = new Set();

      (courses || []).forEach(function (c) {
        const m = extractCourseMonth(c["課程日期"]);
        if (m) {
          monthsSet.add(m);
        }
        const s = String(c["資料來源平台"] || "").trim();
        if (s) {
          sourcesSet.add(s);
        }
      });

      if (monthSelect) {
        const sortedMonths = Array.from(monthsSet).sort().reverse();
        sortedMonths.forEach(function (m) {
          const opt = document.createElement("option");
          opt.value = m;
          opt.textContent = m;
          monthSelect.appendChild(opt);
        });
      }

      if (sourceSelect) {
        const sortedSources = Array.from(sourcesSet).sort();
        sortedSources.forEach(function (s) {
          const opt = document.createElement("option");
          opt.value = s;
          opt.textContent = s;
          sourceSelect.appendChild(opt);
        });
      }
    }

    [keywordInput, creditSelect, modeSelect, feeSelect, monthSelect, sourceSelect].forEach(
      function (control) {
        if (!control) {
          return;
        }
        control.addEventListener("input", applyFiltersAndRender);
        control.addEventListener("change", applyFiltersAndRender);
      }
    );

    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        if (keywordInput) keywordInput.value = "";
        if (creditSelect) creditSelect.value = "";
        if (modeSelect) modeSelect.value = "";
        if (feeSelect) feeSelect.value = "";
        if (monthSelect) monthSelect.value = "";
        if (sourceSelect) sourceSelect.value = "";
        applyFiltersAndRender();
      });
    }

    if (exportFilteredBtn) {
      exportFilteredBtn.addEventListener("click", function () {
        const csvContent = coursesToCsvWithBom(currentFiltered);
        const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "courses-filtered.csv";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      });
    }

    if (sheetsSyncBtn && modalEl) {
      sheetsSyncBtn.addEventListener("click", function () {
        if (formulaInput && typeof window !== "undefined" && window.location) {
          formulaInput.value = buildImportDataFormula(window.location.href);
        }
        if (copyFeedbackEl) {
          copyFeedbackEl.textContent = "";
        }
        modalEl.hidden = false;
      });
    }

    if (closeModalBtn && modalEl) {
      closeModalBtn.addEventListener("click", function () {
        modalEl.hidden = true;
      });
    }

    if (modalEl) {
      modalEl.addEventListener("click", function (ev) {
        if (ev.target === modalEl) {
          modalEl.hidden = true;
        }
      });
    }

    if (copyFormulaBtn && formulaInput) {
      copyFormulaBtn.addEventListener("click", function () {
        const text = formulaInput.value;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () {
            if (copyFeedbackEl) {
              copyFeedbackEl.textContent = "✓ 已複製公式！請至 Google Sheets A1 儲存格貼上。";
            }
          });
        } else {
          formulaInput.select();
          document.execCommand("copy");
          if (copyFeedbackEl) {
            copyFeedbackEl.textContent = "✓ 已複製公式！請至 Google Sheets A1 儲存格貼上。";
          }
        }
      });
    }

    fetch("./data/courses.json")
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("HTTP " + resp.status);
        }
        return resp.json();
      })
      .then(function (payload) {
        allCourses = Array.isArray(payload.courses) ? payload.courses : [];
        if (updatedEl) {
          updatedEl.textContent = "最後更新：" + (payload.updated_at || "未知");
        }
        if (sourceSummaryEl && Array.isArray(payload.source_statuses)) {
          const okCount = payload.source_statuses.filter(function (s) {
            return s.status === "ok";
          }).length;
          sourceSummaryEl.textContent =
            "來源狀態：" + okCount + " / " + payload.source_statuses.length + " 站點連線正常";
        }
        populateDynamicSelects(allCourses);
        applyFiltersAndRender();
      })
      .catch(function (err) {
        tbodyEl.innerHTML =
          '<tr><td colspan="12" class="empty-cell">無法載入課程資料（' +
          escapeHtml(err.message) +
          "）</td></tr>";
      });
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initBrowserApp);
    } else {
      initBrowserApp();
    }
  }

  return {
    COURSE_FIELD_NAMES: COURSE_FIELD_NAMES,
    escapeHtml: escapeHtml,
    extractCourseMonth: extractCourseMonth,
    matchesModeFilter: matchesModeFilter,
    matchesFeeFilter: matchesFeeFilter,
    filterCourses: filterCourses,
    buildImportDataFormula: buildImportDataFormula,
    coursesToCsvWithBom: coursesToCsvWithBom,
  };
});
