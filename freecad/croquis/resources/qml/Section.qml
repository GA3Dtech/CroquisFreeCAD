// SPDX-License-Identifier: LGPL-2.1-or-later
// Croquis - generic panel component. Adapted from ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, dtpanels/qml, LGPL-2.1-or-later).
// Versioned imports: works with Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Rectangle {
    id: sec
    property var th: bridge.theme
    property var section: ({ title: "", params: [] })
    height: body.implicitHeight + 16
    radius: Math.round(6 * th.s)
    color: th.card

    Column {
        id: body
        x: 8; y: 8
        width: sec.width - 16
        spacing: Math.round(4 * th.s)
        Text {
            visible: section.title.length > 0
            text: section.title
            color: th.text
            font.bold: true
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
        }
        Repeater {
            model: section.params
            Loader {
                width: body.width
                visible: bridge.hidden.indexOf(modelData.name) < 0
                height: visible ? implicitHeight : 0
                // initial properties: the row never evaluates its bindings
                // without its parameter and theme
                Component.onCompleted: {
                    var k = modelData.kind
                    if (k === "int") k = "number"
                    setSource(k.charAt(0).toUpperCase() + k.slice(1) + "Row.qml",
                              { "p": modelData, "th": sec.th })
                }
            }
        }
    }
}
