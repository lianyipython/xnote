/**
 * xnote专用ui
 * 依赖库
 *   jquery
 *   layer.js
 * @author xupingmao
 * @since 2017/10/21
 * @modified 2022/04/16 20:24:02
 */


// 调整表格宽度
xnote.table.adjustWidth = function(selector) {
    $(selector).each(function (element, index) {
        var headings = $(this).find("th");
        if (headings.length > 0) {
            var width = 100 / headings.length;
            headings.css("width", width + "%");
        }
    });
};

/**
 * 追加CSS样式表
 * @param {string} styleText 样式文本
 */
xnote.appendCSS = function (styleText) {
    // 居中的样式
    var style = document.createElement("style");
    style.type = "text/css";

    if (style.styleSheet) {
      // 兼容IE
      style.styleSheet.cssText = styleText;  
    } else {  
      style.innerHTML = styleText;
    } 

    document.head.appendChild(style);
}

var XUI = function(window) {
    // 处理select标签选中情况
    function initSelect() {
        $("select").each(function(index, ele) {
            var self = $(ele);
            var children = self.children();
            // 使用$.val() 会取到第一个select标签值
            var value = self.attr("value");
            for (var i = 0; i < children.length; i++) {
                var child = children[i];
                if (value == child.value) {
                    child.selected = "selected";
                }
            }
        });
    }

    function initCheckbox() {
        $("input[type=checkbox]").each(function(index, ele) {
            var self = $(ele);
            var value = self.attr("default-value");
            if (value == "on") {
                self.attr("checked", "checked");
            }
        })
    }

    function initRadio() {
        $("input[type=radio]").each(function(index, ele) {
            var self = $(ele);
            var value = self.attr("default-value");
            if (value == self.val()) {
                self.attr("checked", "checked");
            }
        });
    }

    function initXRadio() {
        $(".x-radio").each(function(index, element) {
            var self = $(element);
            var option = self.attr("data-option");
            var value = self.attr("data-value");
            if (value == option) {
                self.addClass("selected-link");
            }
        });
    };

    // 点击跳转链接的按钮
    $(".link-btn").click(function() {
        var link = $(this).attr("x-href");
        if (!link) {
            link = $(this).attr("href");
        }
        var confirmMessage = $(this).attr("confirm-message");
        if (confirmMessage) {
            xnote.confirm(confirmMessage, function (result) {
                window.location.href = link;
            });
        } else {
            window.location.href = link;
        }
    })

    // 点击prompt按钮
    // <input type="button" class="prompt-btn" action="/rename?name=" message="重命名为" value="重命名">
    $(".prompt-btn").click(function() {
        var action = $(this).attr("action");
        var message = $(this).attr("message");
        var defaultValue = $(this).attr("default-value");
        var inputValue = prompt(message, defaultValue);
        if (inputValue != "" && inputValue) {
            var actionUrl = action + encodeURIComponent(inputValue);
            $.get(actionUrl, function(resp) {
                window.location.reload();
            })
        }
    });

    // 初始化表单控件的默认值
    function initDefaultValue(event) {
        initSelect();
        initCheckbox();
        initRadio();
        initXRadio();
        xnote.table.adjustWidth(".default-table");
    }

    window.xnote.assert = function (expression, message) {
        if (!expression) {
            xnote.alert(message);
        }
    }

    // 刷新各种默认值
    xnote.refresh = function () {
        // 初始化
        initDefaultValue();
        // 注册事件
        xnote.addEventListener("init-default-value", initDefaultValue);
        xnote.addEventListener("xnote.reload", initDefaultValue);
    }

    xnote.refresh();
};

$(document).ready(function() {
    XUI(window);
});
