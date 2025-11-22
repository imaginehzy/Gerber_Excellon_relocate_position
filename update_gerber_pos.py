import re
import os
import sys
import argparse
from pathlib import Path

class GerberCoordinateModifier:
    def __init__(self, input_file):
        self.input_file = input_file
        self.zero_omission = 'L'
        self.coord_format = (3, 6)  # 默认3位整数6位小数
        self.file_unit = 'MM'  # 文件中的单位
        self.input_unit = 'MM'  # 用户输入的单位
        self.aperture_definitions = {}
        self.current_interpolation = 'G01'
        self.quadrant_mode = 'single'
        self.analyze_format()
    
    def analyze_format(self):
        """分析Gerber文件格式"""
        try:
            with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith('%FS'):
                        # 解析格式，如: %FSLAX36Y36*%
                        match = re.search(r'FSL([AT])X(\d)(\d)Y(\d)(\d)', line)
                        if match:
                            self.zero_omission = match.group(1)
                            int_digits_x = int(match.group(2))
                            dec_digits_x = int(match.group(3))
                            int_digits_y = int(match.group(4)) 
                            dec_digits_y = int(match.group(5))
                            self.coord_format = (int_digits_x, dec_digits_x)
                            print(f"  坐标格式: {int_digits_x}.{dec_digits_x} (X{int_digits_x}{dec_digits_x}Y{int_digits_y}{dec_digits_y})")
                    elif line.startswith('%MO'):
                        # 解析单位，如: %MOMM*% 或 %MOIN*%
                        if 'MM' in line:
                            self.file_unit = 'MM'
                            print(f"  文件单位: 毫米(MM)")
                        elif 'IN' in line:
                            self.file_unit = 'IN'  
                            print(f"  文件单位: 英寸(IN)")
                    elif line.startswith('%ADD'):
                        self.extract_aperture_definition(line)
                    
                    if f.tell() > 2000:
                        break
        except Exception as e:
            print(f"  警告: 分析文件格式时出错: {e}，使用默认格式")
    
    def extract_aperture_definition(self, line):
        """提取光圈定义"""
        try:
            match = re.match(r'%ADD(\d+)([CROP]),(.*?)\*%', line)
            if match:
                d_code = match.group(1)
                shape = match.group(2)
                params = match.group(3)
                self.aperture_definitions[d_code] = (shape, params)
        except Exception as e:
            print(f"    警告: 解析光圈定义失败: {e}")
    
    def convert_offset_to_file_units(self, offset_mm, input_unit='MM'):
        """
        将输入的偏移量转换为文件单位的坐标值
        
        参数:
            offset_mm: 偏移量（毫米）
            input_unit: 输入的单位 ('MM' 或 'IN')
        
        返回:
            转换后的坐标整数值
        """
        # 先将输入转换为毫米
        if input_unit == 'IN':
            offset_in_mm = offset_mm * 25.4  # 英寸转毫米
        else:
            offset_in_mm = offset_mm  # 已经是毫米
        
        # 根据文件单位转换
        if self.file_unit == 'IN':
            # 文件使用英寸，将毫米转换为英寸
            offset_in_file_units = offset_in_mm / 25.4
        else:
            # 文件使用毫米，直接使用
            offset_in_file_units = offset_in_mm
        
        # 根据坐标格式转换为整数坐标值
        int_digits, dec_digits = self.coord_format
        multiplier = 10 ** dec_digits  # 小数位数乘数
        
        coordinate_value = int(round(offset_in_file_units * multiplier))
        
        print(f"    偏移转换: {offset_mm}{input_unit} -> {offset_in_file_units:.6f}{self.file_unit} -> 坐标值: {coordinate_value}")
        
        return coordinate_value
    
    def format_coordinate(self, value):
        """根据检测到的格式格式化坐标"""
        int_digits, dec_digits = self.coord_format
        total_digits = int_digits + dec_digits
        
        is_negative = value < 0
        abs_value = abs(value)
        
        if self.zero_omission == 'L':  # 前导零省略
            formatted = str(abs_value).zfill(total_digits)
            return f"-{formatted}" if is_negative else formatted
        else:  # 后导零省略
            return str(value)
    
    def is_arc_command(self, line):
        """检测是否为圆弧命令"""
        line_upper = line.upper().strip()
        return 'G02' in line_upper or 'G03' in line_upper or 'G75' in line_upper
    
    def modify_arc_coordinates(self, line, offset_x, offset_y):
        """专门处理圆弧命令的坐标偏移"""
        patterns = [
            r'^(.*?)(X[-]?\d+)(Y[-]?\d+)(I[-]?\d+)(J[-]?\d+)(D0[123]\*.*)$',
            r'^(.*?)(X[-]?\d+)(I[-]?\d+)(J[-]?\d+)(D0[123]\*.*)$',
            r'^(.*?)(Y[-]?\d+)(I[-]?\d+)(J[-]?\d+)(D0[123]\*.*)$'
        ]
        
        for pattern in patterns:
            match = re.match(pattern, line.strip())
            if match:
                groups = match.groups()
                
                if len(groups) == 6:
                    prefix, x_part, y_part, i_part, j_part, suffix = groups
                    
                    x_val = int(x_part[1:]) + offset_x
                    y_val = int(y_part[1:]) + offset_y
                    i_val = int(i_part[1:])  # I, J 是相对坐标，不需要偏移
                    j_val = int(j_part[1:])
                    
                    x_str = f"X{self.format_coordinate(x_val)}"
                    y_str = f"Y{self.format_coordinate(y_val)}"
                    i_str = f"I{self.format_coordinate(i_val)}"
                    j_str = f"J{self.format_coordinate(j_val)}"
                    
                    return f"{prefix}{x_str}{y_str}{i_str}{j_str}{suffix}\n"
                
                elif len(groups) == 5:
                    prefix, coord1, i_part, j_part, suffix = groups
                    
                    if coord1.startswith('X'):
                        x_val = int(coord1[1:]) + offset_x
                        i_val = int(i_part[1:])
                        j_val = int(j_part[1:])
                        coord1_str = f"X{self.format_coordinate(x_val)}"
                    else:
                        y_val = int(coord1[1:]) + offset_y
                        i_val = int(i_part[1:])
                        j_val = int(j_part[1:])
                        coord1_str = f"Y{self.format_coordinate(y_val)}"
                    
                    i_str = f"I{self.format_coordinate(i_val)}"
                    j_str = f"J{self.format_coordinate(j_val)}"
                    
                    return f"{prefix}{coord1_str}{i_str}{j_str}{suffix}\n"
        
        return line
    
    def modify(self, output_file, offset_x_mm, offset_y_mm, input_unit='MM'):
        """修改坐标 - 支持单位转换"""
        # 转换偏移量为文件单位的坐标值
        offset_x_coord = self.convert_offset_to_file_units(offset_x_mm, input_unit)
        offset_y_coord = self.convert_offset_to_file_units(offset_y_mm, input_unit)
        
        print(f"  最终偏移量 - X: {offset_x_coord}, Y: {offset_y_coord} (坐标值)")
        
        modified_count = 0
        error_count = 0
        arc_commands_found = 0
        
        try:
            with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as f_in, \
                 open(output_file, 'w', encoding='utf-8') as f_out:
                
                for line_num, line in enumerate(f_in, 1):
                    try:
                        original_line = line
                        stripped_line = line.strip()
                        
                        # 保存插补模式状态
                        if stripped_line in ['G01*', 'G02*', 'G03*', 'G75*']:
                            if stripped_line == 'G01*':
                                self.current_interpolation = 'G01'
                            elif stripped_line == 'G02*':
                                self.current_interpolation = 'G02'
                            elif stripped_line == 'G03*':
                                self.current_interpolation = 'G03'
                            elif stripped_line == 'G75*':
                                self.quadrant_mode = 'multi'
                            f_out.write(original_line)
                            continue
                        
                        # 跳过参数块和光圈定义
                        if (line.startswith('%') or 
                            re.match(r'.*D[1-9][0-9]+\*', stripped_line)):
                            f_out.write(original_line)
                            continue
                        
                        # 检查是否为圆弧命令
                        if self.is_arc_command(stripped_line) or self.current_interpolation in ['G02', 'G03']:
                            arc_commands_found += 1
                            modified_line = self.modify_arc_coordinates(stripped_line, offset_x_coord, offset_y_coord)
                            f_out.write(modified_line)
                            if modified_line != original_line:
                                modified_count += 1
                            continue
                        
                        # 处理普通线性坐标
                        match = re.match(r'^(.*?)(X[-]?\d+)(Y[-]?\d+)(D0[123]\*.*)$', stripped_line)
                        
                        if match:
                            prefix, x_part, y_part, suffix = match.groups()
                            
                            x_val = int(x_part[1:]) + offset_x_coord
                            y_val = int(y_part[1:]) + offset_y_coord
                            
                            if x_val < 0 or y_val < 0:
                                print(f"    警告: 行 {line_num} 产生负坐标")
                            
                            x_str = f"X{self.format_coordinate(x_val)}"
                            y_str = f"Y{self.format_coordinate(y_val)}"
                            
                            new_line = f"{prefix}{x_str}{y_str}{suffix}\n"
                            f_out.write(new_line)
                            modified_count += 1
                        else:
                            f_out.write(original_line)
                            
                    except Exception as e:
                        error_count += 1
                        print(f"    处理第 {line_num} 行时出错: {e}")
                        f_out.write(line)
                
                if arc_commands_found > 0:
                    print(f"  检测到 {arc_commands_found} 个圆弧命令，已特殊处理")
                        
            return modified_count, error_count
            
        except Exception as e:
            print(f"  处理文件时发生严重错误: {e}")
            return 0, 1

def find_gerber_files(directory):
    """查找Gerber文件"""
    gerber_extensions = {
        '.gbr', '.gb', '.ger', '.pho', '.gtl', '.gbl', '.gto', '.gbo', 
        '.gts', '.gbs', '.gtp', '.gbp', '.gm1', '.gml', '.gko'
    }
    
    gerber_files = []
    for file_path in Path(directory).iterdir():
        if file_path.is_file() and file_path.suffix.upper() in [ext.upper() for ext in gerber_extensions]:
            gerber_files.append(file_path)
    
    return gerber_files

def main():
    parser = argparse.ArgumentParser(description='Gerber文件坐标偏移工具（智能单位转换版）')
    parser.add_argument('offset_x', type=float, help='X方向偏移量（默认单位：毫米）')
    parser.add_argument('offset_y', type=float, help='Y方向偏移量（默认单位：毫米）')
    parser.add_argument('--input-dir', '-i', default='.', help='输入目录（默认当前目录）')
    parser.add_argument('--input-unit', '-u', choices=['MM', 'IN'], default='MM', 
                       help='输入值的单位（默认：MM）')
    parser.add_argument('--analyze', '-a', action='store_true', help='先分析文件格式')
    
    args = parser.parse_args()
    
    current_dir = Path(args.input_dir).resolve()
    output_dir = current_dir / "output"
    
    print(f"Gerber文件坐标偏移工具（智能单位转换版）")
    print(f"输入偏移量: X={args.offset_x} {args.input_unit}, Y={args.offset_y} {args.input_unit}")
    print(f"输出目录: {output_dir}")
    print("-" * 50)
    
    gerber_files = find_gerber_files(current_dir)
    
    if not gerber_files:
        print("未找到Gerber文件！")
        sys.exit(1)
    
    # 分析阶段
    if args.analyze:
        print("分析阶段：检查文件格式...")
        for file in gerber_files:
            print(f"\n分析文件: {file.name}")
            modifier = GerberCoordinateModifier(file)
        
        proceed = input("\n是否继续处理？(y/n): ")
        if proceed.lower() != 'y':
            return
    
    output_dir.mkdir(exist_ok=True)
    
    total_modified = 0
    total_errors = 0
    
    print("\n开始处理文件...")
    for input_file in gerber_files:
        print(f"\n处理文件: {input_file.name}")
        
        output_file = output_dir / input_file.name
        modifier = GerberCoordinateModifier(input_file)
        
        modified_count, error_count = modifier.modify(output_file, args.offset_x, args.offset_y, args.input_unit)
        
        total_modified += modified_count
        total_errors += error_count
        
        print(f"  完成: 修改了 {modified_count} 个坐标，{error_count} 个错误")
    
    print("\n" + "=" * 50)
    print("处理完成！")
    print(f"总修改坐标: {total_modified} 个")
    print(f"总错误: {total_errors} 个")
    print(f"修改后的文件保存在: {output_dir}")

if __name__ == "__main__":
    main()