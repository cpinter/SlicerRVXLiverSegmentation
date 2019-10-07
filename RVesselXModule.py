import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging
import traceback

from RVesselXModuleLogic import RVesselXModuleLogic
from Vessel import VesselTree, Vessel

_info = logging.info
_warn = logging.warn


def _lineSep(isWarning=False):
  log = _info if not isWarning else _warn
  log('*************************************')


def _warnLineSep():
  _lineSep(isWarning=True)


class RVesselXModule(ScriptedLoadableModule):
  def __init__(self, parent=None):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "R Vessel X"
    self.parent.categories = ["Examples"]
    self.parent.dependencies = []
    self.parent.contributors = ["Lucie Macron - Kitware SAS", "Thibault Pelletier - Kitware SAS"]
    self.parent.helpText = """
        """
    self.parent.acknowledgementText = """
        """


class RVesselXModuleWidget(ScriptedLoadableModuleWidget):
  """Class responsible for the UI of the RVesselX project.

  For more information on the R-Vessel-X project, please visit :
  https://anr.fr/Projet-ANR-18-CE45-0018

  Module is composed of 3 tabs :
    Data Tab : Responsible for loading DICOM data in Slicer
    Liver Tab : Responsible for Liver segmentation
    Vessel Tab : Responsible for vessel segmentation
  """

  def __init__(self, parent=None):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    self.inputSelector = None
    self.volumesModuleSelector = None
    self.volumeRenderingModuleSelector = None
    self.volumeRenderingModuleVisibility = None

    self._vesselStartSelector = None
    self._vesselEndSelector = None
    self._tabWidget = None
    self._liverTab = None
    self._dataTab = None
    self._vesselsTab = None
    self._vesselTree = None
    self._logic = RVesselXModuleLogic()

    # Define layout #
    layoutDescription = """
          <layout type=\"horizontal\" split=\"true\" >
            <item splitSize=\"500\">
              <view class=\"vtkMRMLSliceNode\" singletontag=\"Red\">
              <property name=\"orientation\" action=\"default\">Axial</property>
              <property name=\"viewlabel\" action=\"default\">R</property>
              <property name=\"viewcolor\" action=\"default\">#F34A33</property>
              </view>
            </item>
            <item splitSize=\"500\">
              <view class=\"vtkMRMLViewNode\" singletontag=\"1\">
              <property name=\"viewlabel\" action=\"default\">1</property>
              </view>
            </item>
          </layout>
        """

    layoutNode = slicer.util.getNode('*LayoutNode*')
    if layoutNode.IsLayoutDescription(layoutNode.SlicerLayoutUserView):
      layoutNode.SetLayoutDescription(layoutNode.SlicerLayoutUserView, layoutDescription)
    else:
      layoutNode.AddLayoutDescription(layoutNode.SlicerLayoutUserView, layoutDescription)
    layoutNode.SetViewArrangement(layoutNode.SlicerLayoutUserView)
    self._configure3DViewAsMaximumIntensityProjection()

  def _configure3DViewAsMaximumIntensityProjection(self):
    # Get 3D view Node
    view = slicer.mrmlScene.GetNodeByID('vtkMRMLViewNode1')

    # Set background color to black
    view.SetBackgroundColor2([0, 0, 0])
    view.SetBackgroundColor([0, 0, 0])

    # Set ray cast technique as maximum intensity projection
    # see https://github.com/Slicer/Slicer/blob/master/Libs/MRML/Core/vtkMRMLViewNode.h
    view.SetRaycastTechnique(2)

  def _createTab(self, tab_name):
    tab = qt.QWidget()
    self._tabWidget.addTab(tab, tab_name)
    return tab

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Define module interface #
    moduleCollapsibleButton = ctk.ctkCollapsibleButton()
    moduleCollapsibleButton.text = "R Vessel X"

    self.layout.addWidget(moduleCollapsibleButton)

    # Define main tabulations #
    moduleLayout = qt.QVBoxLayout(moduleCollapsibleButton)

    self._tabWidget = qt.QTabWidget()
    moduleLayout.addWidget(self._tabWidget)

    self._dataTab = self._createTab("Data")
    self._liverTab = self._createTab("Liver")
    self._vesselsTab = self._createTab("Vessels")

    self._configureDataTab()
    self._configureLiverTab()
    self._configureVesselsTab()

    slicer.mrmlScene.AddObserver(slicer.mrmlScene.NodeAddedEvent, self.onNodeAdded)

  def _setCurrentTab(self, tab_widget):
    self._tabWidget.setCurrentWidget(tab_widget)

  def _addInCollapsibleLayout(self, childLayout, parentLayout, collapsibleText, isCollapsed=True):
    """Wraps input childLayout into a collapsible button attached to input parentLayout.
    collapsibleText is writen next to collapsible button. Initial collapsed status is customizable
    (collapsed by default)
    """
    collapsibleButton = ctk.ctkCollapsibleButton()
    collapsibleButton.text = collapsibleText
    collapsibleButton.collapsed = isCollapsed
    parentLayout.addWidget(collapsibleButton)
    qt.QVBoxLayout(collapsibleButton).addWidget(childLayout)

  def _createSingleMarkupFiducial(self, toolTip, markupName, markupColor=qt.QColor("red")):
    seedFiducialsNodeSelector = slicer.qSlicerSimpleMarkupsWidget()
    seedFiducialsNodeSelector.objectName = markupName + 'NodeSelector'
    seedFiducialsNodeSelector.toolTip = toolTip
    seedFiducialsNodeSelector.setNodeBaseName(markupName)
    seedFiducialsNodeSelector.tableWidget().hide()
    seedFiducialsNodeSelector.defaultNodeColor = markupColor
    seedFiducialsNodeSelector.markupsSelectorComboBox().noneEnabled = False
    seedFiducialsNodeSelector.markupsPlaceWidget().placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
    seedFiducialsNodeSelector.setMRMLScene(slicer.mrmlScene)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)', seedFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)')
    return seedFiducialsNodeSelector

  def _extractVessel(self):
    sourceVolume = self.inputSelector.currentNode()
    startPoint = self._vesselStartSelector.currentNode()
    endPoint = self._vesselEndSelector.currentNode()

    vessel = self._logic.extractVessel(sourceVolume=sourceVolume, startPoint=startPoint, endPoint=endPoint)
    self._vesselTree.addVessel(vessel)

    # Set vessel start node as end node and remove end node selection for easier leaf selection for user
    self._vesselStartSelector.setCurrentNode(self._vesselEndSelector.currentNode())
    self._vesselEndSelector.setCurrentNode(None)

    # Reselect source volume as volume input (running logic deselects volume somehow)
    self.inputSelector.setCurrentNode(sourceVolume)

  def _createExtractVesselLayout(self):
    formLayout = qt.QFormLayout()

    # Start point fiducial
    vesselPointName = "vesselPoint"
    self._vesselStartSelector = self._createSingleMarkupFiducial("Select vessel start position", vesselPointName)
    formLayout.addRow("Vessel Start:", self._vesselStartSelector)

    # End point fiducial
    self._vesselEndSelector = self._createSingleMarkupFiducial("Select vessel end position", vesselPointName)
    formLayout.addRow("Vessel End:", self._vesselEndSelector)

    # Extract Vessel Button
    extractVesselButton = qt.QPushButton("Extract Vessel")
    extractVesselButton.connect("clicked(bool)", self._extractVessel)
    extractVesselButton.setToolTip(
      "Select vessel start point, vessel end point, and volume then press Extract button to extract vessel")
    formLayout.addRow("", extractVesselButton)

    # Enable extract button when all selector nodes are correctly set
    def updateExtractButtonStatus():
      def getNode(node):
        return node.currentNode()

      def fiducialSelected(seedSelector):
        return getNode(seedSelector) and getNode(seedSelector).GetNumberOfFiducials() > 0

      isButtonEnabled = getNode(self.inputSelector) and fiducialSelected(
        self._vesselStartSelector) and fiducialSelected(self._vesselEndSelector)
      extractVesselButton.setEnabled(isButtonEnabled)

    self.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", updateExtractButtonStatus)
    self._vesselStartSelector.connect("updateFinished()", updateExtractButtonStatus)
    self._vesselEndSelector.connect("updateFinished()", updateExtractButtonStatus)

    return formLayout

  def _createInputNodeSelector(self, nodeType, toolTip, callBack=None):
    inputSelector = slicer.qMRMLNodeComboBox()
    inputSelector.nodeTypes = [nodeType]
    inputSelector.selectNodeUponCreation = False
    inputSelector.addEnabled = False
    inputSelector.removeEnabled = False
    inputSelector.noneEnabled = False
    inputSelector.showHidden = False
    inputSelector.showChildNodeTypes = False
    inputSelector.setMRMLScene(slicer.mrmlScene)
    inputSelector.setToolTip(toolTip)
    if callBack is not None:
      inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", callBack)
    return inputSelector

  def _configureDataTab(self):
    dataTabLayout = qt.QVBoxLayout(self._dataTab)

    # Add load MRI button #
    inputLayout = qt.QHBoxLayout()

    inputLabel = qt.QLabel("Volume: ")
    inputLayout.addWidget(inputLabel)
    self.inputSelector = self._createInputNodeSelector("vtkMRMLScalarVolumeNode", toolTip="Pick the input.",
                                                       callBack=self.onInputSelectorNodeChanged)

    inputLayout.addWidget(self.inputSelector)

    loadDicomButton = qt.QPushButton("Load DICOM")
    loadDicomButton.connect("clicked(bool)", self.onLoadDMRIClicked)
    inputLayout.addWidget(loadDicomButton)

    loadDataButton = qt.QPushButton("Load Data")
    loadDataButton.connect("clicked(bool)", self.onLoadDataClicked)
    inputLayout.addWidget(loadDataButton)

    dataTabLayout.addLayout(inputLayout)

    # Add Volume information
    volumesWidget = slicer.util.getNewModuleGui(slicer.modules.volumes)
    self._addInCollapsibleLayout(volumesWidget, dataTabLayout, "Volume")

    # Hide Volumes Selector and its label
    activeVolumeNodeSelectorName = "ActiveVolumeNodeSelector"
    widgetToRemoveNames = ["ActiveVolumeLabel", activeVolumeNodeSelectorName]

    for child in volumesWidget.children():
      if child.name in widgetToRemoveNames:
        child.visible = False

      if child.name == activeVolumeNodeSelectorName:
        self.volumesModuleSelector = child

    # Add Volume Rendering information
    volumeRenderingWidget = slicer.util.getNewModuleGui(slicer.modules.volumerendering)
    self._addInCollapsibleLayout(volumeRenderingWidget, dataTabLayout, "Volume Rendering")

    # Hide Volume Rendering Selector and its label
    visibilityCheckboxName = "VisibilityCheckBox"
    volumeNodeSelectorName = "VolumeNodeComboBox"

    for child in volumeRenderingWidget.children():
      if child.name == visibilityCheckboxName:
        child.visible = False
        self.volumeRenderingModuleVisibility = child
      if child.name == volumeNodeSelectorName:
        child.visible = False
        self.volumeRenderingModuleSelector = child

    # Add stretch
    dataTabLayout.addStretch(1)

    # Add Next/Previous arrow
    dataTabLayout.addLayout(self._createPreviousNextArrowsLayout(next_tab=self._liverTab))

  def _configureLiverTab(self):
    """ Liver tab contains segmentation utils for extracting the liver in the input DICOM.

    Direct include of Segmentation Editor is done.
    """
    liverTabLayout = qt.QVBoxLayout(self._liverTab)
    segmentationUi = slicer.util.getNewModuleGui(slicer.modules.segmenteditor)
    liverTabLayout.addWidget(segmentationUi)

    liverTabLayout.addLayout(
      self._createPreviousNextArrowsLayout(previous_tab=self._dataTab, next_tab=self._vesselsTab))

  def _configureVesselsTab(self):
    """ Vessels Tab interfaces the Vessels Modelisation ToolKit in one aggregated view.

    Integration includes :
        Vesselness filtering : visualization help to extract vessels
        Level set segmentation : segmentation tool for the vessels
        Center line computation : Extraction of the vessels endpoints from 3D vessels and start point
        Vessels tree : View tree to select, add, show / hide vessels
    """
    # Visualisation tree for Vessels
    vesselsTabLayout = qt.QVBoxLayout(self._vesselsTab)

    self._vesselTree = VesselTree()
    vesselsTabLayout.addWidget(self._vesselTree.getWidget())
    vesselsTabLayout.addLayout(self._createExtractVesselLayout())

    # Add vessel previous and next button (next button will be disabled)
    vesselsTabLayout.addLayout(self._createPreviousNextArrowsLayout(previous_tab=self._liverTab))

  def _createTabButton(self, buttonIcon, nextTab=None):
    """
    Creates a button linking to a given input tab. If input tab is None, button will be disabled
    
    Parameters 
    ----------
    buttonIcon
      Icon for the button
    nextTab
      Next tab which will be set when button is clicked
    
    Returns 
    -------
      QPushButton
    """
    tabButton = qt.QPushButton()
    tabButton.setIcon(buttonIcon)
    if nextTab is not None:
      tabButton.connect('clicked()', lambda tab=nextTab: self._setCurrentTab(tab))
    else:
      tabButton.enabled = False
    return tabButton

  def _createPreviousNextArrowsLayout(self, previous_tab=None, next_tab=None):
    """ Creates HBox layout with previous and next arrows pointing to previous Tab and Next tab given as input.

    If input tabs are None, button will be present but disabled.

    Parameters
    ----------
    previous_tab
      Tab set when clicking on left arrow
    next_tab
      Tab set when clicking on right arrow

    Returns
    -------
    QHBoxLayout
      Layout with previous and next arrows pointing to input tabs
    """
    # Create previous / next arrows
    previousIcon = qt.QApplication.style().standardIcon(qt.QStyle.SP_ArrowLeft)
    previousButton = self._createTabButton(previousIcon, previous_tab)

    nextIcon = qt.QApplication.style().standardIcon(qt.QStyle.SP_ArrowRight)
    nextButton = self._createTabButton(nextIcon, next_tab)

    # Add arrows to Horizontal layout and return layout
    buttonHBoxLayout = qt.QHBoxLayout()
    buttonHBoxLayout.addWidget(previousButton)
    buttonHBoxLayout.addWidget(nextButton)
    return buttonHBoxLayout

  def onLoadDMRIClicked(self):
    # Show DICOM Widget #
    try:
      dicomWidget = slicer.modules.DICOMWidget
    except:
      dicomWidget = slicer.modules.dicom.widgetRepresentation().self()

    if dicomWidget is not None:
      dicomWidget.detailsPopup.open()

  def onLoadDataClicked(self):
    slicer.app.ioManager().openAddDataDialog()

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def onNodeAdded(self, caller, event, calldata):
    if isinstance(calldata, slicer.vtkMRMLVolumeNode):
      layoutNode = slicer.util.getNode('*LayoutNode*')
      layoutNode.SetViewArrangement(layoutNode.SlicerLayoutUserView)
      self.setCurrentNode(calldata)

  def onInputSelectorNodeChanged(self):
    node = self.inputSelector.currentNode()

    if node is not None:
      # Update current node on volume and volumeRendering modules
      self.setCurrentNode(node)

      # Show volume
      slicer.util.setSliceViewerLayers(node)

      # Call showVolumeRendering using a timer instead of calling it directly
      # to allow the volume loading to fully complete.
      qt.QTimer.singleShot(0, lambda: self.showVolumeRendering(node))

  def setCurrentNode(self, node):
    self.inputSelector.setCurrentNode(node)

    if self.volumesModuleSelector:
      self.volumesModuleSelector.setCurrentNode(node)

    if self.volumeRenderingModuleSelector:
      self.volumeRenderingModuleSelector.setCurrentNode(node)

  def showVolumeRendering(self, volumeNode):
    volRenLogic = slicer.modules.volumerendering.logic()
    displayNode = volRenLogic.CreateDefaultVolumeRenderingNodes(volumeNode)
    displayNode.SetVisibility(True)
    slicer.util.resetThreeDViews()

    # Load preset
    # https://www.slicer.org/wiki/Documentation/Nightly/ScriptRepository#Show_volume_rendering_automatically_when_a_volume_is_loaded
    scalarRange = volumeNode.GetImageData().GetScalarRange()
    if scalarRange[1] - scalarRange[0] < 1500:
      # small dynamic range, probably MRI
      displayNode.GetVolumePropertyNode().Copy(volRenLogic.GetPresetByName('MR-Default'))
    else:
      # larger dynamic range, probably CT
      displayNode.GetVolumePropertyNode().Copy(volRenLogic.GetPresetByName('CT-Chest-Contrast-Enhanced'))


class RVesselXModuleTest(ScriptedLoadableModuleTest):
  def setUp(self):
    """ Clear scene before each tests
    """
    slicer.mrmlScene.Clear(0)

  def _listTests(self):
    """
    Returns
    -------
    List of every test in test class
    """
    return [func for func in dir(self) if func.startswith('test') and callable(getattr(self, func))]

  def runTest(self):
    """ Runs each test and aggregates results in a list
    """

    className = type(self).__name__
    _info('Running Tests %s' % className)
    _lineSep()

    testList = self._listTests()

    success_count = 0
    failed_name = []
    nTest = len(testList)
    _info("Discovered tests : %s" % testList)
    _lineSep()
    for iTest, testName in enumerate(testList):
      self.setUp()
      test = getattr(self, testName)
      debugTestName = '%s/%s' % (className, testName)
      try:
        _info('Test Start (%d/%d) : %s' % (iTest + 1, nTest, debugTestName))
        test()
        success_count += 1
        _info('Test OK!')
        _lineSep()
      except Exception:
        _warn('Test NOK!')
        _warn(traceback.format_exc())
        failed_name.append(debugTestName)
        _warnLineSep()

    success_count_str = 'Succeeded %d/%d tests' % (success_count, len(testList))
    if success_count != len(testList):
      _warnLineSep()
      _warn('Testing Failed!')
      _warn(success_count_str)
      _warn('Failed tests names : %s' % failed_name)
      _warnLineSep()
    else:
      _lineSep()
      _info('Testing OK!')
      _info(success_count_str)
      _lineSep()

  def _cropSourceVolume(self, sourceVolume, roi):
    cropVolumeNode = slicer.vtkMRMLCropVolumeParametersNode()
    cropVolumeNode.SetScene(slicer.mrmlScene)
    cropVolumeNode.SetName(sourceVolume.GetName() + "Cropped")
    cropVolumeNode.SetIsotropicResampling(True)
    cropVolumeNode.SetSpacingScalingConst(0.5)
    slicer.mrmlScene.AddNode(cropVolumeNode)

    cropVolumeNode.SetInputVolumeNodeID(sourceVolume.GetID())
    cropVolumeNode.SetROINodeID(roi.GetID())

    cropVolumeLogic = slicer.modules.cropvolume.logic()
    cropVolumeLogic.Apply(cropVolumeNode)

    return cropVolumeNode.GetOutputVolumeNode()

  def _emptyVolume(self, volumeName):
    emptyVolume = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
    emptyVolume.UnRegister(None)
    emptyVolume.SetName(slicer.mrmlScene.GetUniqueNameByString(volumeName))
    return emptyVolume

  def _createVesselWithArbitraryData(self, vesselName=None):
    from itertools import count
    v = Vessel(vesselName)
    pt = ([i, 0, 0] for i in count(start=0, step=1))

    startPoint = RVesselXModuleLogic._createFiducialNode("startPoint", next(pt))
    endPoint = RVesselXModuleLogic._createFiducialNode("endPoint", next(pt))
    seedPoints = RVesselXModuleLogic._createFiducialNode("seedPoint", next(pt), next(pt))

    segmentationVol = self._emptyVolume("segVolume")
    vesselVol = self._emptyVolume("vesselVolume")
    segmentationModel = RVesselXModuleLogic._createModelNode("segModel")
    centerlineModel = RVesselXModuleLogic._createModelNode("centerlineModel")
    voronoiModel = RVesselXModuleLogic._createModelNode("voronoiModel")

    # Create volumes associated with vessel extraction
    v.setExtremities(startPoint=startPoint, endPoint=endPoint)
    v.setSegmentation(seeds=seedPoints, volume=segmentationVol, model=segmentationModel)
    v.setCenterline(centerline=centerlineModel, voronoiModel=voronoiModel)
    v.setVesselnessVolume(vesselnessVolume=vesselVol)
    return v

  def testVesselSegmentationLogic(self):
    # load test data
    import SampleData
    sampleDataLogic = SampleData.SampleDataLogic()
    sourceVolume = sampleDataLogic.downloadCTACardio()

    # Create start point and end point for the vessel extraction
    startPosition = [176.9, -17.4, 52.7]
    endPosition = [174.704, -23.046, 76.908]

    startPoint = RVesselXModuleLogic._createFiducialNode("startPoint", startPosition)
    endPoint = RVesselXModuleLogic._createFiducialNode("endPoint", endPosition)

    # Crop volume
    roi = slicer.vtkMRMLAnnotationROINode()
    roi.Initialize(slicer.mrmlScene)
    roi.SetName("VolumeCropROI")
    roi.SetXYZ(startPosition[0], startPosition[1], startPosition[2])
    radius = max(abs(a - b) for a, b in zip(startPosition, endPosition)) * 2
    roi.SetRadiusXYZ(radius, radius, radius)

    sourceVolume = self._cropSourceVolume(sourceVolume, roi)

    # Run vessel extraction and expect non empty values and data
    logic = RVesselXModuleLogic()
    vessel = logic.extractVessel(sourceVolume, startPoint, endPoint)

    self.assertIsNotNone(vessel.segmentedVolume)
    self.assertIsNotNone(vessel.segmentedModel)
    self.assertNotEqual(0, vessel.segmentedModel.GetPolyData().GetNumberOfCells())
    self.assertIsNotNone(vessel.segmentedCenterline)
    self.assertNotEqual(0, vessel.segmentedCenterline.GetPolyData().GetNumberOfCells())

  def testVesselCreationNameIsInSegmentationName(self):
    v = self._createVesselWithArbitraryData()
    self.assertIn(v.name, v.segmentedVolume.GetName())
    self.assertIn(v.name, v.segmentedModel.GetName())
    self.assertIn(v.name, v.segmentedCenterline.GetName())

  def testOnRenameRenamesSegmentationName(self):
    v = self._createVesselWithArbitraryData()
    newName = "New Name"
    v.name = newName
    self.assertEqual(newName, v.name)
    self.assertIn(v.name, v.segmentedVolume.GetName())
    self.assertIn(v.name, v.segmentedModel.GetName())
    self.assertIn(v.name, v.segmentedCenterline.GetName())

  def testOnDeleteVesselRemovesAllAssociatedModelsFromSceneExceptStartAndEndPoints(self):
    # Create a vessel
    vessel = self._createVesselWithArbitraryData()

    # Add vessel to tree widget
    tree = VesselTree()
    treeItem = tree.addVessel(vessel)

    # Remove vessel from scene using the delete button trigger
    tree.triggerVesselButton(treeItem, VesselTree.ColumnIndex.delete)

    # Assert the different models are no longer in the scene
    self.assertFalse(slicer.mrmlScene.IsNodePresent(vessel.vesselnessVolume))
    self.assertFalse(slicer.mrmlScene.IsNodePresent(vessel.segmentationSeeds))
    self.assertFalse(slicer.mrmlScene.IsNodePresent(vessel.segmentedVolume))
    self.assertFalse(slicer.mrmlScene.IsNodePresent(vessel.segmentedModel))
    self.assertFalse(slicer.mrmlScene.IsNodePresent(vessel.segmentedCenterline))
    self.assertFalse(slicer.mrmlScene.IsNodePresent(vessel.segmentedVoronoiModel))

    # Assert start and end points are still kept in the scene even after delete
    self.assertTrue(slicer.mrmlScene.IsNodePresent(vessel.startPoint))
    self.assertTrue(slicer.mrmlScene.IsNodePresent(vessel.endPoint))

  def testDeleteLeafVesselRemovesItemFromTree(self):
    # Create a vesselRoot and leaf
    vesselParent = self._createVesselWithArbitraryData("parent")
    vesselLeaf = self._createVesselWithArbitraryData("leaf")
    vesselLeaf.startPoint = vesselParent.endPoint

    # Add vessel to tree widget
    tree = VesselTree()
    treeItem = tree.addVessel(vesselParent)
    treeLeafItem = tree.addVessel(vesselLeaf)

    # Remove vessel from scene using the delete button trigger
    tree.triggerVesselButton(treeLeafItem, VesselTree.ColumnIndex.delete)

    # Verify leaf is not associated with parent
    self.assertEqual(0, treeItem.childCount())

    # verify leaf is not part of the tree
    self.assertFalse(tree.containsItem(treeLeafItem))

  def testDeleteRootVesselRemovesAssociatedLeafs(self):
    # Create vessels and setup hierarchy
    vesselParent = self._createVesselWithArbitraryData("parent")
    vesselChild = self._createVesselWithArbitraryData("child")
    vesselChild.startPoint = vesselParent.endPoint

    vesselChild2 = self._createVesselWithArbitraryData("child 2")
    vesselChild2.startPoint = vesselParent.endPoint

    vesselChild3 = self._createVesselWithArbitraryData("child 3")
    vesselChild3.startPoint = vesselParent.endPoint

    vesselSubChild = self._createVesselWithArbitraryData("sub child")
    vesselSubChild.startPoint = vesselChild.endPoint

    vesselSubChild2 = self._createVesselWithArbitraryData("sub child 2")
    vesselSubChild2.startPoint = vesselChild3.endPoint

    # Create tree and add vessels to the tree
    tree = VesselTree()
    treeItemParent = tree.addVessel(vesselParent)
    treeItemChild = tree.addVessel(vesselChild)
    treeItemChild2 = tree.addVessel(vesselChild2)
    treeItemChild3 = tree.addVessel(vesselChild3)
    treeItemSubChild = tree.addVessel(vesselSubChild)
    treeItemSubChild2 = tree.addVessel(vesselSubChild2)

    # Remove child 1 and expect child and sub to be deleted
    tree.triggerVesselButton(treeItemChild, VesselTree.ColumnIndex.delete)
    self.assertFalse(tree.containsItem(treeItemChild))
    self.assertFalse(tree.containsItem(treeItemSubChild))

    # Remove root and expect all to be deleted
    tree.triggerVesselButton(treeItemParent, VesselTree.ColumnIndex.delete)
    self.assertFalse(tree.containsItem(treeItemParent))
    self.assertFalse(tree.containsItem(treeItemChild2))
    self.assertFalse(tree.containsItem(treeItemChild3))
    self.assertFalse(tree.containsItem(treeItemSubChild2))

  def testOnAddingVesselWithStartPointIdenticalToOtherVesselEndPointAddsVesselAsChildOfOther(self):
    # Create vessels and setup hierarchy
    vesselParent = self._createVesselWithArbitraryData("parent")
    vesselChild = self._createVesselWithArbitraryData("child")
    vesselChild.startPoint = vesselParent.endPoint

    vesselChild2 = self._createVesselWithArbitraryData("child 2")
    vesselChild2.startPoint = vesselParent.endPoint

    vesselSubChild = self._createVesselWithArbitraryData("sub child")
    vesselSubChild.startPoint = vesselChild.endPoint

    # Create tree and add vessels to the tree
    tree = VesselTree()
    treeItemParent = tree.addVessel(vesselParent)
    treeItemChild = tree.addVessel(vesselChild)
    treeItemChild2 = tree.addVessel(vesselChild2)
    treeItemSubChild = tree.addVessel(vesselSubChild)

    # Verify hierarchy
    self.assertEqual(2, treeItemParent.childCount())
    self.assertEqual(1, treeItemChild.childCount())

    self.assertEqual(treeItemParent, treeItemChild.parent())
    self.assertEqual(treeItemParent, treeItemChild2.parent())
    self.assertEqual(treeItemChild, treeItemSubChild.parent())
