// SPDX-License-Identifier: LGPL-2.1-or-later
// Croquis - generic panel component. Adapted from ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, dtpanels/qml, LGPL-2.1-or-later).
// Versioned imports: works with Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
// Generic panel: everything comes from the "bridge" context object
// (bridge.py), built from a panel model (panel_model.py).
import QtQuick 2.15

Rectangle {
    id: root
    property var th: bridge.theme
    property real contentHeight: col.implicitHeight + 16
    color: th.window
    onContentHeightChanged: bridge.setContentHeight(contentHeight)
    Component.onCompleted: bridge.setContentHeight(contentHeight)

    Column {
        id: col
        x: 8; y: 8
        width: root.width - 16
        spacing: Math.round(8 * th.s)

        Text {
            width: parent.width
            visible: text.length > 0
            text: bridge.hint
            color: th.muted
            wrapMode: Text.WordWrap
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
        }
        Repeater {
            model: bridge.sections
            Section { th: root.th; section: modelData; width: col.width }
        }
        Flow {
            width: parent.width
            spacing: Math.round(6 * th.s)
            visible: bridge.actions.length > 0
            Repeater {
                model: bridge.actions
                PillButton {
                    th: root.th
                    label: modelData.label
                    primary: modelData.primary === true
                    onClicked: bridge.trigger(modelData.name)
                }
            }
        }
        Rectangle {
            width: parent.width
            height: err.implicitHeight + 12
            radius: Math.round(6 * th.s)
            visible: bridge.error.length > 0
            color: "transparent"
            border.color: th.bad
            Text {
                id: err
                x: 8; y: 6
                width: parent.width - 16
                text: bridge.error
                color: th.bad
                wrapMode: Text.WordWrap
                font.pixelSize: Math.round(12 * th.s); font.family: th.family
            }
        }
    }
}
