import re
import pandas as pd
import streamlit as st
from io import BytesIO


st.title("IOS_T0_EXCEL")

show_run_file = st.file_uploader(
    "Upload show run output",
    type=["txt"],
    key="show_run"
)

show_int_status_file = st.file_uploader(
    "Upload show interface status output",
    type=["txt"],
    key="int_status"
)

show_cdp_file = st.file_uploader(
    "Upload show cdp neighbors detail output",
    type=["txt"],
    key="cdp"
)

def read_uploaded_txt(uploaded_file):
    raw = uploaded_file.getvalue()

    try:
        return raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return raw.decode("latin-1").splitlines()


if show_run_file and show_int_status_file and show_cdp_file:
    st.success("All files uploaded successfully")

    show_run_lines = read_uploaded_txt(show_run_file)
    show_int_status_lines = read_uploaded_txt(show_int_status_file)
    show_cdp_lines = read_uploaded_txt(show_cdp_file)

    def normalize_interface_name(if_name):  
        if not if_name:
            return if_name

        if if_name.startswith("Eth"):
            return if_name.replace("Eth", "Ethernet", 1)
        elif if_name.startswith("Gi"):
            return if_name.replace("Gi", "GigabitEthernet", 1)
        elif if_name.startswith("Te"):
            return if_name.replace("Te", "TenGigabitEthernet", 1)
        elif if_name.startswith("Po"):
            return if_name.replace("Po", "Port-channel", 1)
        else:
            return if_name
        
    

# ================== PARSE SHOW RUN ==================
    def parse_show_run(show_run_file):
        interfaces = {}
        current_interface = None

       
        for line in show_run_file:
            line = line.strip()

            if line.startswith("interface"):
                current_interface = line.split()[1]
                interfaces[current_interface] = {
                    "Description": "",
                    "VLANs": "",
                    "IP Address": "",
                    "Port Channel": ""
                }

            elif current_interface:
                if line.startswith("description"):
                    interfaces[current_interface]["Description"] = line.replace("description", "").strip()

                elif line == "shutdown":
                    interfaces[current_interface]["Shutdown"] = "down"

                elif line.startswith("ip address"):
                    interfaces[current_interface]["IP Address"] = " ".join(line.split()[2:])

                elif "switchport access vlan" in line:
                    interfaces[current_interface]["VLANs"] = line.split()[-1]

                elif "switchport trunk allowed vlan" in line:
                    interfaces[current_interface]["VLANs"] = line.split()[-1]

                elif line.startswith("channel-group"):
                    channel_number = line.split()[1]
                    interfaces[current_interface]["Port Channel"] = f"Port-channel{channel_number}"

        return interfaces


# ================== PARSE SHOW INTERFACE STATUS ==================

    def detect_columns(header_line):
        """
        Detect column names and their start positions from header line
        """
        columns = []
        for match in re.finditer(r"\S+", header_line):
            col_name = match.group()
            start = match.start()
            columns.append((col_name, start))
        return columns


    def parse_ios_show_interface_status(lines):
        interfaces = {}

        header = lines[0]
        column_defs = detect_columns(header)

        # Build slice ranges
        slices = []
        for i in range(len(column_defs)):
            col_name, start = column_defs[i]
            end = column_defs[i + 1][1] if i + 1 < len(column_defs) else None
            slices.append((col_name, start, end))

        # Parse data rows
        for line in lines[1:]:
            if not line.strip():
                continue

            row = {}
            for col_name, start, end in slices:
                value = line[start:end].strip() if end else line[start:].strip()
                row[col_name] = value

            port = row.get("Port")
            if port:
                port = normalize_interface_name(port)

                interfaces[port] = row.get("Status", "")
            
                

        return interfaces

    def read_txt_file(file_path):
        
        return file_path.decode("utf-8", errors="ignore").splitlines()
        

    def parse_show_interface_status(int_status_file): 
        int_status_file = parse_ios_show_interface_status(int_status_file)
        return int_status_file



# ================== PARSE SHOW CDP NEIGHBORS ==================
    def parse_show_cdp_neighbors(show_cdp_file):
        """
        Parse IOS 'show cdp neighbors detail' output.
        Returns:
            {
                local_interface: {
                    'Neighbour': device_id,
                    'Neighbour Interface': neighbor_port
                }
            }
        """

        cdp_neighbors = {}

        current_device = None
        local_interface = None
        neighbor_interface = None

        
        for line in show_cdp_file:
                line = line.strip()

                if not line:
                    continue

                # Device ID
                if line.startswith("Device ID:"):
                    current_device = line.split(":", 1)[1].strip()
                    continue

                # Interface line
                if line.startswith("Interface:") and "Port ID" in line:
                    # Example:
                    # Interface: GigabitEthernet0/1,  Port ID (outgoing port): GigabitEthernet1/0/24
                    try:
                        left, right = line.split(",  Port ID (outgoing port):", 1)

                        local_interface =left.replace("Interface:", "").strip()
                    
                        neighbor_interface = right.strip()

                        if current_device and local_interface:
                            cdp_neighbors[local_interface] = {
                                "Neighbour": current_device,
                                "Neighbour Interface": neighbor_interface
                            }

                    except ValueError:
                        continue

        return cdp_neighbors



# ================== MAIN ==================

    show_run_data = parse_show_run(show_run_lines)
    interface_status_data = parse_show_interface_status(show_int_status_lines)
    cdp_neighbor_data = parse_show_cdp_neighbors(show_cdp_lines)

    rows = []

    for interface, data in show_run_data.items():
        row = {
            "Interface": interface,
            "Description": data["Description"],
            "Status": interface_status_data.get(interface),
            "VLANs": data["VLANs"],
            "IP Address": data["IP Address"],
            "Port Channel": data["Port Channel"],
            "Neighbour": cdp_neighbor_data.get(interface, {}).get("Neighbour", ""),
            "Neighbour Interface": cdp_neighbor_data.get(interface, {}).get("Neighbour Interface", "")
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(df)

    def dataframe_to_excel_bytes(df):
        output = BytesIO()
        df.to_excel(output, index=False, engine="openpyxl")
        output.seek(0)
        return output


    excel_file = dataframe_to_excel_bytes(df)

    st.download_button(
        "Download Excel",
        data=excel_file,
        file_name="switch_interfaces.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

#if __name__ == "__main__":
 #   main()





