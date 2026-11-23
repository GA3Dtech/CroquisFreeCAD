// SPDX-License-Identifier: LGPL-2.1-or-later
// Croquis - paper / layers palette of the drawing board.
// Custom QML (rule 2): a compact palette next to the drawing area, with
// paper chips, eye toggles and live opacity sliders, clearly better in
// Qt Quick than stacked group boxes. Fallback: canvas/view.py LayersPanel.
// Driven by the "layers" context object (bridge.LayersBridge).
// Versioned imports: works with Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Rectangle {
    id: root
    property var th: layers.theme
    color: th.window
    implicitHeight: col.implicitHeight + 16

    Column {
        id: col
        x: 8; y: 8
        width: root.width - 16
        spacing: Math.round(10 * th.s)

        Text {
            text: i18n.tr("Paper")
            color: th.text
            font.bold: true
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
        }
        Flow {
            width: parent.width
            spacing: Math.round(6 * th.s)
            Repeater {
                model: layers.papers
                Rectangle {
                    objectName: "paper_" + modelData.key
                    property bool sel: modelData.key === layers.paper
                    width: Math.round(30 * th.s); height: width; radius: width / 2
                    color: modelData.color.length > 0 ? modelData.color : "#ffffff"
                    border.width: sel ? 3 : 1
                    border.color: sel ? th.accent : th.line
                    // transparent paper: a checker hint
                    Grid {
                        visible: modelData.color.length === 0
                        anchors.centerIn: parent
                        columns: 2
                        Repeater {
                            model: 4
                            Rectangle {
                                width: Math.round(8 * th.s); height: width
                                color: (index === 0 || index === 3) ? "#cfcfcf" : "#ffffff"
                            }
                        }
                    }
                    MouseArea {
                        id: pm
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: layers.setPaper(modelData.key)
                    }
                    Rectangle {     // tooltip
                        visible: pm.containsMouse
                        z: 10
                        y: parent.height + 2
                        width: tip.implicitWidth + 10; height: tip.implicitHeight + 6
                        radius: 4
                        color: th.card
                        border.color: th.line
                        Text {
                            id: tip
                            anchors.centerIn: parent
                            text: modelData.label
                            color: th.text
                            font.pixelSize: Math.round(11 * th.s); font.family: th.family
                        }
                    }
                }
            }
        }

        Text {
            text: i18n.tr("Layers")
            color: th.text
            font.bold: true
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
        }
        Repeater {
            model: layers.layers
            Rectangle {
                objectName: "layer_" + modelData.key
                width: col.width
                height: Math.round(52 * th.s)
                radius: Math.round(6 * th.s)
                color: th.card
                opacity: modelData.visible ? 1.0 : 0.6

                Rectangle {     // eye toggle
                    id: eye
                    x: 6; y: Math.round(6 * th.s)
                    width: Math.round(22 * th.s); height: width; radius: width / 2
                    color: modelData.visible ? th.accent : th.field
                    border.color: th.line
                    Rectangle {
                        anchors.centerIn: parent
                        width: parent.width * 0.36; height: width; radius: width / 2
                        color: modelData.visible ? th.accentText : th.muted
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: layers.setVisible(modelData.key, !modelData.visible)
                    }
                }
                Text {
                    anchors.left: eye.right; anchors.leftMargin: 8
                    anchors.right: pct.left
                    y: Math.round(8 * th.s)
                    text: modelData.label
                    color: th.text
                    elide: Text.ElideRight
                    font.pixelSize: Math.round(12 * th.s); font.family: th.family
                }
                Text {
                    id: pct
                    anchors.right: parent.right; anchors.rightMargin: 8
                    y: Math.round(8 * th.s)
                    text: Math.round(modelData.opacity * 100) + " %"
                    color: th.muted
                    font.pixelSize: Math.round(11 * th.s); font.family: th.family
                }
                Item {          // opacity slider
                    id: track
                    x: 8; width: parent.width - 16
                    y: Math.round(32 * th.s); height: Math.round(14 * th.s)
                    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: 3; radius: 2; color: th.line }
                    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: parent.width * modelData.opacity; height: 3; radius: 2; color: th.accent }
                    Rectangle {
                        x: (parent.width - width) * modelData.opacity
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.round(12 * th.s); height: width; radius: width / 2
                        color: th.text
                        border.width: 2; border.color: th.accent
                    }
                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -4
                        preventStealing: true
                        function pick(mx) {
                            layers.setOpacity(modelData.key, Math.max(0, Math.min(1, mx / track.width)))
                        }
                        onPressed: function(mouse) { pick(mouse.x) }
                        onPositionChanged: function(mouse) { if (pressed) pick(mouse.x) }
                    }
                }
            }
        }
    }
}
