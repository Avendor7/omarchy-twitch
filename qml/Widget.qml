import QtQuick
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "avendor7.twitch"

  property var snapshot: ({ streams: [], follows: [], config: { poll_interval: 90 } })
  readonly property int liveCount: snapshot.streams ? snapshot.streams.length : 0

  function injectPanel() {
    if (!panelLoader.item) return
    panelLoader.item.bar = root.bar
    panelLoader.item.anchorItem = button
    panelLoader.item.hostWidget = root
  }

  function refresh() {
    if (panelLoader.item) panelLoader.item.refresh(false)
  }

  function open() {
    if (panelLoader.item) panelLoader.item.open()
  }

  function close() {
    if (panelLoader.item) panelLoader.item.close()
  }

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened : false
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing : false

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  onBarChanged: injectPanel()

  Loader {
    id: panelLoader
    active: true
    visible: false
    source: Qt.resolvedUrl("Panel.qml")
    onLoaded: root.injectPanel()
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "● " + root.liveCount
    foreground: Color.accent
    tooltipText: root.liveCount + " followed channels live"
    active: root.opened
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.MiddleButton) root.refresh()
      else if (panelLoader.item) panelLoader.item.toggle()
    }
  }
}
