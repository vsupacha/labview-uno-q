<?xml version='1.0' encoding='UTF-8'?>
<Project Type="Project" LVVersion="21008000">
	<Item Name="My Computer" Type="My Computer">
		<Property Name="server.app.propertiesEnabled" Type="Bool">true</Property>
		<Property Name="server.control.propertiesEnabled" Type="Bool">true</Property>
		<Property Name="server.tcp.enabled" Type="Bool">false</Property>
		<Property Name="server.tcp.port" Type="Int">0</Property>
		<Property Name="server.tcp.serviceName" Type="Str">My Computer/VI Server</Property>
		<Property Name="server.tcp.serviceName.default" Type="Str">My Computer/VI Server</Property>
		<Property Name="server.vi.callsEnabled" Type="Bool">true</Property>
		<Property Name="server.vi.propertiesEnabled" Type="Bool">true</Property>
		<Property Name="specify.custom.address" Type="Bool">false</Property>
		<Item Name="Arduino API" Type="Folder">
			<Item Name="UNO Q AnalogRead.vi" Type="VI" URL="../UNO Q AnalogRead.vi"/>
			<Item Name="UNO Q DigitalRead.vi" Type="VI" URL="../UNO Q DigitalRead.vi"/>
			<Item Name="UNO Q DigitalWrite.vi" Type="VI" URL="../UNO Q DigitalWrite.vi"/>
			<Item Name="UNO Q LED control.vi" Type="VI" URL="../UNO Q LED control.vi"/>
			<Item Name="UNO Q PinMode.vi" Type="VI" URL="../UNO Q PinMode.vi"/>
		</Item>
		<Item Name="Typedef" Type="Folder">
			<Item Name="Apin typedef.ctl" Type="VI" URL="../Apin typedef.ctl"/>
			<Item Name="Dpin typedef.ctl" Type="VI" URL="../Dpin typedef.ctl"/>
			<Item Name="ERR typedef.ctl" Type="VI" URL="../ERR typedef.ctl"/>
			<Item Name="LED typedef.ctl" Type="VI" URL="../LED typedef.ctl"/>
			<Item Name="UNO Q Session.ctl" Type="VI" URL="../UNO Q Session.ctl"/>
		</Item>
		<Item Name="UNO Q API" Type="Folder">
			<Item Name="UNO Q connect.vi" Type="VI" URL="../UNO Q connect.vi"/>
			<Item Name="UNO Q disconnect.vi" Type="VI" URL="../UNO Q disconnect.vi"/>
		</Item>
		<Item Name="Demo - blink.vi" Type="VI" URL="../Demo - blink.vi"/>
		<Item Name="Demo - din.vi" Type="VI" URL="../Demo - din.vi"/>
		<Item Name="Demo - dout.vi" Type="VI" URL="../Demo - dout.vi"/>
		<Item Name="Demo - plot.vi" Type="VI" URL="../Demo - plot.vi"/>
		<Item Name="Dependencies" Type="Dependencies">
			<Item Name="vi.lib" Type="Folder">
				<Item Name="Check if File or Folder Exists.vi" Type="VI" URL="/&lt;vilib&gt;/Utility/libraryn.llb/Check if File or Folder Exists.vi"/>
				<Item Name="Error Cluster From Error Code.vi" Type="VI" URL="/&lt;vilib&gt;/Utility/error.llb/Error Cluster From Error Code.vi"/>
				<Item Name="LabVIEWHTTPClient.lvlib" Type="Library" URL="/&lt;vilib&gt;/httpClient/LabVIEWHTTPClient.lvlib"/>
				<Item Name="NI_FileType.lvlib" Type="Library" URL="/&lt;vilib&gt;/Utility/lvfile.llb/NI_FileType.lvlib"/>
				<Item Name="NI_PackedLibraryUtility.lvlib" Type="Library" URL="/&lt;vilib&gt;/Utility/LVLibp/NI_PackedLibraryUtility.lvlib"/>
				<Item Name="Path To Command Line String.vi" Type="VI" URL="/&lt;vilib&gt;/AdvancedString/Path To Command Line String.vi"/>
				<Item Name="PathToUNIXPathString.vi" Type="VI" URL="/&lt;vilib&gt;/Platform/CFURL.llb/PathToUNIXPathString.vi"/>
				<Item Name="subTimeDelay.vi" Type="VI" URL="/&lt;vilib&gt;/express/express execution control/TimeDelayBlock.llb/subTimeDelay.vi"/>
			</Item>
		</Item>
		<Item Name="Build Specifications" Type="Build"/>
	</Item>
</Project>
