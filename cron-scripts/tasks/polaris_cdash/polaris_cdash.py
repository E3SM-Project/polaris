import argparse
import platform
import time
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os
import sys
import glob
import re
import shutil

# Shared Utilities

def get_system_info():
    info = {}
    info['OSName'] = platform.system()
    info['Hostname'] = platform.node()
    info['OSRelease'] = platform.release()
    info['OSVersion'] = platform.version()
    info['OSPlatform'] = platform.machine()
    info['Is64Bits'] = "1" if sys.maxsize > 2**32 else "0"
    
    try:
        import psutil
        info['NumberOfLogicalCPU'] = str(psutil.cpu_count(logical=True))
        info['NumberOfPhysicalCPU'] = str(psutil.cpu_count(logical=False))
        info['TotalPhysicalMemory'] = str(int(psutil.virtual_memory().total / (1024 * 1024))) # MB
    except ImportError:
        info['NumberOfLogicalCPU'] = "1"
        info['NumberOfPhysicalCPU'] = "1"
        info['TotalPhysicalMemory'] = "1024"

    info['VendorString'] = "Unknown"
    info['VendorID'] = "Unknown"
    info['FamilyID'] = "0"
    info['ModelID'] = "0"
    info['ProcessorCacheSize'] = "0"
    info['ProcessorClockFrequency'] = "0"
    
    return info

def strip_ansi_codes(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def read_tag_file(results_dir):
    tag_path = os.path.join(results_dir, "TAG")
    if not os.path.exists(tag_path):
        raise FileNotFoundError(f"TAG file not found at {tag_path}")
        
    with open(tag_path, 'r') as f:
        lines = [line.strip() for line in f.readlines()]
        
    if len(lines) < 2:
        raise ValueError(f"TAG file at {tag_path} contains fewer than 2 lines.")
        
    folder_name = lines[0]
    group_name = lines[1]
    
    # "Joining the two lines of TAG with '-' is a BUILD_STAMP"
    build_stamp = f"{folder_name}-{group_name}"
    
    return folder_name, build_stamp

def process_build_xml(args, folder_name, build_stamp, sys_info):
    # "there is a folder with the same name to the first line of TAG file. in the folder, there is Build.xml"
    source_build_xml = os.path.join(args.results_dir, folder_name, "Build.xml")
    
    if not os.path.exists(source_build_xml):
        print(f"Warning: Build.xml not found at {source_build_xml}. Generating minimal Build.xml instead.")
        # Fallback or error? User said "Use it instead of generating it."
        # I'll try to generate a minimal one if missing, but primarily we expect it.
        # For now let's error if strictly required, but safer to warn.
        # Actually user instructions imply it exists. I will error if not found to be explicit.
        raise FileNotFoundError(f"Source Build.xml not found at {source_build_xml}")

    print(f"Reading Build.xml from {source_build_xml}")
    tree = ET.parse(source_build_xml)
    site = tree.getroot()
    if site.tag != "Site":
        # Check if root is Site, sometimes it might be different? XML usually <Site ...>
        # CTest XMLs usually start with Site.
        pass
        
    # "Modify BuildName of Site node with --build-name argument."
    # "Also change Name of Site node with --site-name argument."
    if args.build_name:
        site.set("BuildName", args.build_name)
    
    if args.site_name:
        site.set("Name", args.site_name)
        
    # Ensure BuildStamp is set to the one from TAG
    site.set("BuildStamp", build_stamp)
    
    # Add system info updates if needed? 
    # The existing Build.xml might have system info.
    # User didn't fetch system info explicitly for Build.xml, but we used to add it.
    # Let's preserve existing attributes unless we need to overwrite.
    # But usually <Site> has OS info. We can update it if missing or just trust existing.
    # User instruction: "In Build.xml modify [Names]... Also... use [Names]... of Test.xml... to the same data to Build.xml"
    # Doesn't explicitly say "update OS info". I will leave OS info as is from the source file.

    xmlstr = minidom.parseString(ET.tostring(site)).toprettyxml(indent="\t")
    
    output_path = os.path.join(args.output_dir, "Build.xml")
    with open(output_path, "w") as f:
        f.write(xmlstr)
    print(f"Generated {output_path} (copied and modified from source)")
    
    return site.attrib # Return attributes for Test.xml usage

def generate_test_xml(args, site_attribs, sys_info):
    # Same structure as before, but using site_attribs for the Site element
    site = ET.Element("Site")
    
    # Copy attributes from Build.xml's Site element
    for k, v in site_attribs.items():
        site.set(k, v)
        
    # Ensure our CLI args override if not already (process_build_xml updated the attribs, so they should be correct)
    
    testing = ET.SubElement(site, "Testing")
    
    start_time = int(time.time())
    formatted_start_time = time.strftime("%b %d %H:%M %Z", time.localtime(start_time))
    ET.SubElement(testing, "StartDateTime").text = formatted_start_time
    ET.SubElement(testing, "StartTestTime").text = str(start_time)
    
    test_list = ET.SubElement(testing, "TestList")
    
    log_files = glob.glob(os.path.join(args.log_dir, "*.log"))
    log_files.sort()
    
    tests = []
    
    if not log_files:
        print(f"Warning: No log files found in {args.log_dir}")
        
    for log_file in log_files:
        filename = os.path.basename(log_file)
        test_name = filename
        
        try:
            with open(log_file, 'r', errors='replace') as f:
                content = f.read()
                content = strip_ansi_codes(content)
        except Exception as e:
            content = f"Error reading file: {e}"
        
        if "POLARIS TASK: PASS" not in content:
            status = "failed"
        elif "POLARIS BASELINE:" in content and "POLARIS BASELINE: PASS" not in content:
            status = "failed"
        else:
            status = "passed"
        
        tests.append({
            'name': test_name,
            'status': status,
            'output': content,
            'path': log_file
        })
        
        ET.SubElement(test_list, "Test").text = f"./{args.log_dir}/{test_name}"
        
    for test_data in tests:
        test_elem = ET.SubElement(testing, "Test", Status=test_data['status'])
        ET.SubElement(test_elem, "Name").text = test_data['name']
        ET.SubElement(test_elem, "Path").text = f"./{args.log_dir}"
        ET.SubElement(test_elem, "FullName").text = f"./{args.log_dir}/{test_data['name']}"
        ET.SubElement(test_elem, "FullCommandLine").text = f"cat {test_data['path']}"
        
        results = ET.SubElement(test_elem, "Results")
        
        named_meas_time = ET.SubElement(results, "NamedMeasurement", type="numeric/double", name="Execution Time")
        ET.SubElement(named_meas_time, "Value").text = "1.0"
        
        named_meas_status = ET.SubElement(results, "NamedMeasurement", type="text/string", name="Completion Status")
        ET.SubElement(named_meas_status, "Value").text = "Completed"
        
        named_meas_cmd = ET.SubElement(results, "NamedMeasurement", type="text/string", name="Command Line")
        ET.SubElement(named_meas_cmd, "Value").text = f"cat {test_data['path']}"
        
        measurement = ET.SubElement(results, "Measurement")
        ET.SubElement(measurement, "Value").text = test_data['output']
        
    formatted_end_time = time.strftime("%b %d %H:%M %Z", time.localtime(int(time.time())))
    ET.SubElement(testing, "EndDateTime").text = formatted_end_time
    ET.SubElement(testing, "EndTestTime").text = str(int(time.time()))
    
    output_path = os.path.join(args.output_dir, "Test.xml")
    tree = ET.ElementTree(site)
    tree.write(output_path, encoding="UTF-8", xml_declaration=True)
    print(f"Generated {output_path}")

def generate_done_xml(args, build_id):
    root = ET.Element("Done")
    ET.SubElement(root, "buildId").text = build_id
    ET.SubElement(root, "time").text = str(int(time.time()))

    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(indent="\t")
    output_path = os.path.join(args.output_dir, "Done.xml")
    with open(output_path, "w") as f:
        f.write(xmlstr)
    print(f"Generated {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Generate CDash XML files from log directory")
    
    parser.add_argument("--log-dir", required=True, help="Directory containing log files")
    parser.add_argument("--results-dir", required=True, help="Directory containing TAG file and Build.xml subdirectory")
    # Removed --build-stamp
    parser.add_argument("--site-name", required=True, help="Name of the site")
    # Build name defaults to log folder name, but can be overridden
    parser.add_argument("--build-name", help="Name of the build") 
    parser.add_argument("--build-id", required=True, help="ID of the build")
    
    parser.add_argument("--output-dir", default=".", help="Directory to output XML files")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    if not args.build_name:
        args.build_name = os.path.basename(os.path.normpath(args.log_dir))
        
    sys_info = get_system_info()
    
    # 1. Read TAG
    folder_name, build_stamp = read_tag_file(args.results_dir)
    print(f"Detected BuildStamp: {build_stamp} (from {args.results_dir}/TAG)")
    
    # 2. Process Build.xml
    site_attribs = process_build_xml(args, folder_name, build_stamp, sys_info)
    
    # 3. Generate Test.xml using same Site attribs
    generate_test_xml(args, site_attribs, sys_info)
    
    # 4. Generate Done.xml
    generate_done_xml(args, args.build_id)

if __name__ == "__main__":
    main()
