import re
import os
import sys
import argparse
from pathlib import Path

class DrillCoordinateModifier:
    def __init__(self, input_file):
        self.input_file = input_file
        self.file_unit = 'MM'  # 文件中的单位
        self.input_unit = 'MM'  # 用户输入的单位
        self.is_drill_file = False
        self.file_encoding = self.detect_encoding()
        self.analyze_format()
    
    def detect_encoding(self):
        """检测文件编码"""
        encodings = ['utf-8', 'gbk', 'latin-1', 'ascii']
        
        for encoding in encodings:
            try:
                with open(self.input_file, 'r', encoding=encoding) as f:
                    f.read(1024)
                print(f"  文件编码: {encoding}")
                return encoding
            except UnicodeDecodeError:
                continue
        
        print("  警告: 无法检测编码，使用utf-8并忽略错误")
        return 'utf-8'
    
    def analyze_format(self):
        """分析钻孔文件格式"""
        try:
            with open(self.input_file, 'r', encoding=self.file_encoding, errors='ignore') as f:
                content = f.read()
                content_upper = content.upper()
                
                # 检查是否为Excellon格式的钻孔文件
                drill_indicators = [
                    'M48', 'M72', 'M71', 'INCH', 'METRIC', 'FMAT', 
                    'T01C', 'T02C', 'T1C', 'T2C'
                ]
                
                indicator_count = sum(1 for indicator in drill_indicators if indicator in content_upper)
                self.is_drill_file = indicator_count >= 2
                
                if self.is_drill_file:
                    print(f"  确认为钻孔文件，找到 {indicator_count} 个特征标识")
                    
                    # 解析单位
                    if 'METRIC' in content_upper:
                        self.file_unit = 'MM'
                        print(f"  文件单位: 毫米(METRIC)")
                    elif 'INCH' in content_upper:
                        self.file_unit = 'IN'
                        print(f"  文件单位: 英寸(INCH)")
                    else:
                        print(f"  文件单位: 默认毫米(MM)")
                        
                else:
                    print(f"  警告: 未识别为钻孔文件")
                    
        except Exception as e:
            print(f"  分析文件格式时出错: {e}")
            self.is_drill_file = False
    
    def convert_offset_to_file_units(self, offset_mm, input_unit='MM'):
        """
        将输入的偏移量转换为文件单位的偏移量
        
        参数:
            offset_mm: 偏移量（毫米）
            input_unit: 输入的单位 ('MM' 或 'IN')
        
        返回:
            转换后的偏移量（文件单位）
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
        
        print(f"    偏移转换: {offset_mm}{input_unit} -> {offset_in_file_units:.6f}{self.file_unit}")
        
        return offset_in_file_units
    
    def parse_coordinate(self, coord_str):
        """解析坐标字符串为浮点数"""
        # 去掉X或Y前缀，直接转换为浮点数
        return float(coord_str[1:])
    
    def format_coordinate(self, value):
        """将坐标值格式化为字符串，去掉前导零"""
        # 直接使用浮点数格式，不添加前导零
        return f"{value:.6f}".rstrip('0').rstrip('.')  # 去掉多余的零和小数点
    
    def modify(self, output_file, offset_x_mm, offset_y_mm, input_unit='MM'):
        """修改钻孔文件坐标 - 正确的单位转换"""
        if not self.is_drill_file:
            print(f"  跳过: 不是有效的钻孔文件")
            try:
                with open(self.input_file, 'r', encoding=self.file_encoding, errors='ignore') as f_in, \
                     open(output_file, 'w', encoding='utf-8') as f_out:
                    f_out.write(f_in.read())
            except Exception as e:
                print(f"  复制文件时出错: {e}")
            return 0, 0
        
        # 转换偏移量为文件单位的偏移量
        offset_x_file = self.convert_offset_to_file_units(offset_x_mm, input_unit)
        offset_y_file = self.convert_offset_to_file_units(offset_y_mm, input_unit)
        
        print(f"  最终偏移量 - X: {offset_x_file:.6f}{self.file_unit}, Y: {offset_y_file:.6f}{self.file_unit}")
        
        modified_count = 0
        error_count = 0
        
        try:
            with open(self.input_file, 'r', encoding=self.file_encoding, errors='ignore') as f_in, \
                 open(output_file, 'w', encoding='utf-8') as f_out:
                
                for line_num, line in enumerate(f_in, 1):
                    try:
                        original_line = line
                        stripped_line = line.strip()
                        
                        # 跳过空行和结束命令
                        if not stripped_line or stripped_line in ['M30', 'M00', 'M02']:
                            f_out.write(original_line)
                            continue
                        
                        # 刀具选择命令 - 原样写入
                        if re.match(r'^T\d+', stripped_line):
                            f_out.write(original_line)
                            continue
                        
                        # 匹配坐标模式 - 支持小数点和负号
                        coord_match = re.match(r'^(.*?)(X[-\d.]+)(.*?)(Y[-\d.]+)(.*)$', stripped_line)
                        
                        if coord_match:
                            prefix, x_part, middle, y_part, suffix = coord_match.groups()
                            
                            # 解析坐标值（浮点数）
                            x_val = self.parse_coordinate(x_part)
                            y_val = self.parse_coordinate(y_part)
                            
                            # 应用偏移
                            new_x = x_val + offset_x_file
                            new_y = y_val + offset_y_file
                            
                            # 格式化新坐标（去掉前导零）
                            x_str = f"X{self.format_coordinate(new_x)}"
                            y_str = f"Y{self.format_coordinate(new_y)}"
                            
                            new_line = f"{prefix}{x_str}{middle}{y_str}{suffix}\n"
                            f_out.write(new_line)
                            modified_count += 1
                            
                            if modified_count <= 3:
                                print(f"    坐标修改: {x_part}{middle}{y_part}")
                                print(f"              -> {x_str}{middle}{y_str}")
                                print(f"              计算: {x_val:.3f} + {offset_x_file:.3f} = {new_x:.3f}")
                                print(f"                   {y_val:.3f} + {offset_y_file:.3f} = {new_y:.3f}")
                            
                        else:
                            # 检查单独的X坐标
                            single_x_match = re.match(r'^(.*?)(X[-\d.]+)(.*)$', stripped_line)
                            if single_x_match:
                                prefix, x_part, suffix = single_x_match.groups()
                                x_val = self.parse_coordinate(x_part)
                                new_x = x_val + offset_x_file
                                x_str = f"X{self.format_coordinate(new_x)}"
                                new_line = f"{prefix}{x_str}{suffix}\n"
                                f_out.write(new_line)
                                modified_count += 1
                                if modified_count <= 3:
                                    print(f"    X坐标修改: {x_part} -> {x_str}")
                                    print(f"              计算: {x_val:.3f} + {offset_x_file:.3f} = {new_x:.3f}")
                                continue
                            
                            # 检查单独的Y坐标
                            single_y_match = re.match(r'^(.*?)(Y[-\d.]+)(.*)$', stripped_line)
                            if single_y_match:
                                prefix, y_part, suffix = single_y_match.groups()
                                y_val = self.parse_coordinate(y_part)
                                new_y = y_val + offset_y_file
                                y_str = f"Y{self.format_coordinate(new_y)}"
                                new_line = f"{prefix}{y_str}{suffix}\n"
                                f_out.write(new_line)
                                modified_count += 1
                                if modified_count <= 3:
                                    print(f"    Y坐标修改: {y_part} -> {y_str}")
                                    print(f"              计算: {y_val:.3f} + {offset_y_file:.3f} = {new_y:.3f}")
                                continue
                            
                            # 其他命令原样写入
                            f_out.write(original_line)
                            
                    except Exception as e:
                        error_count += 1
                        print(f"    第 {line_num} 行出错: {e}")
                        print(f"    问题行: {stripped_line}")
                        f_out.write(original_line)
                
                if modified_count == 0:
                    print(f"  ⚠ 警告: 没有找到可修改的坐标")
                        
            return modified_count, error_count
            
        except Exception as e:
            print(f"  处理文件时发生严重错误: {e}")
            try:
                with open(self.input_file, 'r', encoding=self.file_encoding, errors='ignore') as f_in, \
                     open(output_file, 'w', encoding='utf-8') as f_out:
                    f_out.write(f_in.read())
            except Exception as copy_error:
                print(f"  文件复制也失败: {copy_error}")
            return 0, 1

def find_drill_files(directory):
    """查找钻孔文件"""
    drill_files = []
    
    for file_path in Path(directory).iterdir():
        if file_path.is_file():
            filename_lower = file_path.name.lower()
            
            # 主要钻孔文件扩展名
            if file_path.suffix.lower() in ['.drl', '.drd', '.txt', '.nc']:
                if any(keyword in filename_lower for keyword in 
                       ['drill', 'drl', 'drd', 'nc_drill', 'nc']) or \
                   file_path.suffix.lower() in ['.drl', '.drd']:
                    drill_files.append(file_path)
    
    return drill_files

def main():
    parser = argparse.ArgumentParser(description='钻孔文件坐标偏移工具（正确单位转换版）')
    parser.add_argument('offset_x', type=float, help='X方向偏移量（默认单位：毫米）')
    parser.add_argument('offset_y', type=float, help='Y方向偏移量（默认单位：毫米）')
    parser.add_argument('--input-dir', '-i', default='.', help='输入目录（默认当前目录）')
    parser.add_argument('--input-unit', '-u', choices=['MM', 'IN'], default='MM', 
                       help='输入值的单位（默认：MM）')
    parser.add_argument('--debug', '-d', action='store_true', help='调试模式')
    
    args = parser.parse_args()
    
    current_dir = Path(args.input_dir).resolve()
    output_dir = current_dir / "output"
    
    print(f"钻孔文件坐标偏移工具（正确单位转换版）")
    print(f"输入偏移量: X={args.offset_x} {args.input_unit}, Y={args.offset_y} {args.input_unit}")
    print(f"输出目录: {output_dir}")
    print("-" * 50)
    
    drill_files = find_drill_files(current_dir)
    
    if not drill_files:
        print("未找到钻孔文件！")
        sys.exit(1)
    
    print(f"找到 {len(drill_files)} 个钻孔文件:")
    for file in drill_files:
        print(f"  - {file.name}")
    
    output_dir.mkdir(exist_ok=True)
    
    total_modified = 0
    total_errors = 0
    valid_drill_files = 0
    
    print("\n开始处理文件...")
    for input_file in drill_files:
        print(f"\n处理文件: {input_file.name}")
        
        output_file = output_dir / input_file.name
        modifier = DrillCoordinateModifier(input_file)
        
        modified_count, error_count = modifier.modify(output_file, args.offset_x, args.offset_y, args.input_unit)
        
        if modifier.is_drill_file:
            valid_drill_files += 1
        
        total_modified += modified_count
        total_errors += error_count
        
        if modified_count > 0:
            print(f"  ✓ 成功修改 {modified_count} 个坐标")
        else:
            print(f"  ⚠ 没有修改任何坐标")
    
    print("\n" + "=" * 50)
    print("处理完成！")
    print(f"有效钻孔文件: {valid_drill_files}/{len(drill_files)}")
    print(f"总修改坐标: {total_modified} 个")
    print(f"总错误: {total_errors} 个")
    print(f"修改后的文件保存在: {output_dir}")

if __name__ == "__main__":
    main()