import heapq
import struct
import os

from engine.common.io_stats import touch

ACTIVO = -1
SIN_LIBRES = -1
FIN_LIBRES = -2


class RID:
    def __init__(self, page_id, slot_id):
        self.page_id=page_id
        self.slot_id=slot_id

    def getter(self):
        return self.page_id, self.slot_id

    def __eq__(self, other):
        return self.page_id == other.page_id and self.slot_id == other.slot_id

class Heapfile:
    def __init__(self, filename, page_size, record_format):
        self.FILE_HEADER_FORMAT = "iiii" #tamaño de pagina, total de paginas, total de registros, first page id
        self.PAGE_HEADER_FORMAT = "iiii" #id, numero de registros, numero de registros activos, free list head
        self.filename=filename
        self.PAGE_SIZE=page_size
        self.RECORD_FORMAT=record_format+"i"
        self.RECORD_SIZE = struct.calcsize(self.RECORD_FORMAT)
        self.FILE_HEADER_SIZE=struct.calcsize(self.FILE_HEADER_FORMAT)
        self.PAGE_HEADER_SIZE = struct.calcsize(self.PAGE_HEADER_FORMAT)
        self.SLOT_PER_PAGE=(page_size-self.PAGE_HEADER_SIZE)//self.RECORD_SIZE
        if self.SLOT_PER_PAGE <= 0:
            raise ValueError("page_size es demasiado pequeño para el header y el registro")
        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            with open(filename, "wb") as f:
                f.write(struct.pack(self.FILE_HEADER_FORMAT, self.PAGE_SIZE,0,0,1))
                f.write(b"\x00" * (self.PAGE_SIZE - self.FILE_HEADER_SIZE))
        self._cargar_mapa_libres()

    def _cargar_mapa_libres(self):
        self._con_huecos = set()
        self._orden_huecos = []
        total_pages = self.read_file_header()[1]
        for page_id in range(1, total_pages + 1):
            if self.read_page_header(page_id)[3] != SIN_LIBRES:
                self._marcar_hueco(page_id)

    def _marcar_hueco(self, page_id):
        if page_id not in self._con_huecos:
            self._con_huecos.add(page_id)
            heapq.heappush(self._orden_huecos, page_id)

    def _pagina_con_hueco(self):
        while self._orden_huecos:
            page_id = self._orden_huecos[0]
            if page_id in self._con_huecos and self.read_page_header(page_id)[3] != SIN_LIBRES:
                return page_id
            heapq.heappop(self._orden_huecos)
            self._con_huecos.discard(page_id)
        return None

    def calcular_slot(self, page_id, slot_id):
        return (self.PAGE_SIZE*page_id)+self.PAGE_HEADER_SIZE+(slot_id*self.RECORD_SIZE)
    
    def read_file_header(self):
        touch(self.filename, 0)
        with open(self.filename,"rb") as f:
            f.seek(0)
            data=f.read(self.FILE_HEADER_SIZE)            
            page_size, tot_pag, tot_reg, first_id=struct.unpack(self.FILE_HEADER_FORMAT, data)
            return page_size, tot_pag, tot_reg, first_id
        
    def read_page_header(self,page_id):
        touch(self.filename, page_id)
        with open(self.filename, "rb") as f:
            f.seek(self.PAGE_SIZE*page_id)
            data=f.read(self.PAGE_HEADER_SIZE)
            id, num_reg, reg_act, free_list=struct.unpack(self.PAGE_HEADER_FORMAT, data)
            return id, num_reg, reg_act, free_list

    def write_file_header(self, page_size, total_pages, total_records, first_page_id):
        touch(self.filename, 0)
        with open(self.filename, "r+b") as f:
            f.seek(0)
            f.write(struct.pack(self.FILE_HEADER_FORMAT, page_size, total_pages, total_records, first_page_id))

    def write_page_header(self, page_id, num_reg, reg_act, free_list_head):
        touch(self.filename, page_id)
        with open(self.filename, "r+b") as f:
            f.seek(page_id * self.PAGE_SIZE)
            f.write(struct.pack(self.PAGE_HEADER_FORMAT, page_id, num_reg, reg_act, free_list_head))
        
    def new_page(self):
        with open(self.filename, "r+b") as f:
            page_size, tot_pag, tot_reg, first_id=self.read_file_header()
            new_page_id=tot_pag+1
            touch(self.filename, new_page_id)

            page_offset=new_page_id*self.PAGE_SIZE
            f.seek(page_offset)

            page_header=struct.pack(self.PAGE_HEADER_FORMAT, new_page_id, 0, 0, -1)
            f.write(page_header)
            f.write(b"\x00" * (self.PAGE_SIZE - self.PAGE_HEADER_SIZE))

            tot_pag=tot_pag+1
            f.seek(0)
            f.write(struct.pack(self.FILE_HEADER_FORMAT, page_size, tot_pag, tot_reg, first_id))

        return new_page_id

    def actualizar_file_header(self, añadir_pagina, añadir_registro):
        with open(self.filename, "r+b") as f:
            page_size, num_paginas, num_records, first_id=self.read_file_header()
            if(añadir_pagina):
                num_paginas+=1
            if(añadir_registro):
                num_records+=1
            f.seek(0)
            f.write(struct.pack(self.FILE_HEADER_FORMAT,self.PAGE_SIZE, num_paginas, num_records, 1))

    def actualizar_page_header(self, page_id ,nuevo_registro, eliminar_registro, nuevo_free_list_head=-1):
        with open(self.filename, "r+b") as f:
            id, num_registros, num_activos, free_list=self.read_page_header(page_id)
            if nuevo_registro:
                num_registros+=1
                num_activos+=1
            if eliminar_registro:
                num_activos-=1
            if(nuevo_free_list_head!=-1):
                free_list=nuevo_free_list_head
            f.seek(page_id*self.PAGE_SIZE)
            f.write(struct.pack(self.PAGE_HEADER_FORMAT, id, num_registros, num_activos, free_list))

    def _puntero(self, f, page_id, slot_id):
        f.seek(self.calcular_slot(page_id, slot_id) + self.RECORD_SIZE - struct.calcsize("i"))
        return struct.unpack("i", f.read(struct.calcsize("i")))[0]

    def _escribir_registro(self, f, page_id, slot_id, registro):
        f.seek(self.calcular_slot(page_id, slot_id))
        f.write(struct.pack(self.RECORD_FORMAT, *registro, ACTIVO))

    def _sumar_registros(self, cantidad):
        page_size, total_pages, total_records, first_id = self.read_file_header()
        self.write_file_header(page_size, total_pages, max(0, total_records + cantidad), first_id)

    def insert(self, *registro):
        with open(self.filename, "r+b") as f:
            page_size, tot_pag, tot_reg, first_id = self.read_file_header()
            page_id = self._pagina_con_hueco()
            if page_id is not None:
                page_id_leido, num_reg, reg_act, free_list = self.read_page_header(page_id)
                slot_id = free_list
                siguiente = self._puntero(f, page_id, slot_id)
                if siguiente == FIN_LIBRES:
                    siguiente = SIN_LIBRES
                    self._con_huecos.discard(page_id)
                self._escribir_registro(f, page_id, slot_id, registro)
                self.write_page_header(page_id, num_reg, reg_act + 1, siguiente)
                self._sumar_registros(1)
                return RID(page_id, slot_id)
            if tot_pag > 0:
                page_id_leido, num_reg, reg_act, free_list = self.read_page_header(tot_pag)
                if num_reg < self.SLOT_PER_PAGE:
                    slot_id = num_reg
                    self._escribir_registro(f, tot_pag, slot_id, registro)
                    self.write_page_header(tot_pag, num_reg + 1, reg_act + 1, free_list)
                    self._sumar_registros(1)
                    return RID(tot_pag, slot_id)
        new_page_id = self.new_page()
        with open(self.filename, "r+b") as f:
            self._escribir_registro(f, new_page_id, 0, registro)
        self.write_page_header(new_page_id, 1, 1, SIN_LIBRES)
        self._sumar_registros(1)
        return RID(new_page_id, 0)

    def delete(self, rid):
        page_id, slot_id = rid.getter()
        page_id_leido, num_reg, reg_act, free_list = self.read_page_header(page_id)
        if slot_id >= num_reg:
            raise ValueError("RID no válido")
        with open(self.filename, "r+b") as f:
            if self._puntero(f, page_id, slot_id) != ACTIVO:
                return False
            siguiente = free_list
            if siguiente == SIN_LIBRES:
                siguiente = FIN_LIBRES
            f.seek(self.calcular_slot(page_id, slot_id) + self.RECORD_SIZE - struct.calcsize("i"))
            f.write(struct.pack("i", siguiente))
        self.write_page_header(page_id, num_reg, reg_act - 1, slot_id)
        self._marcar_hueco(page_id)
        self._sumar_registros(-1)
        return True

    def update(self, rid, nuevos_datos):
        page_id, slot_id = rid.getter()
        touch(self.filename, page_id)
        slot_offset = self.calcular_slot(page_id, slot_id)
        with open(self.filename, "r+b") as f:
            f.seek(slot_offset)
            raw = f.read(self.RECORD_SIZE)
            if len(raw) < self.RECORD_SIZE:
                raise ValueError("RID no válido o slot vacío")
            record = struct.unpack(self.RECORD_FORMAT, raw)
            if record[-1] != ACTIVO:
                raise ValueError("No se puede actualizar un slot libre")
            data = record[:-1]
            if len(nuevos_datos) != len(data):
                raise ValueError("Hay menos campos de los esperados")
            f.seek(slot_offset)
            f.write(struct.pack(self.RECORD_FORMAT, *nuevos_datos, -1))
        return True

    def search(self, campo_index, valor_buscado):
        resultados = []
        with open(self.filename, "rb") as f:
            page_size, total_pages, total_records, first_id = self.read_file_header()
            for page_id in range(1, total_pages + 1):
                page_id_leido, num_reg, reg_act, free_list = self.read_page_header(page_id)
                for slot_id in range(num_reg):
                    slot_offset = self.calcular_slot(page_id, slot_id)
                    f.seek(slot_offset)
                    raw = f.read(self.RECORD_SIZE)
                    if len(raw) < self.RECORD_SIZE:
                        continue
                    record = struct.unpack(self.RECORD_FORMAT, raw)
                    next_free = record[-1]
                    if next_free != ACTIVO:
                        continue
                    data = record[:-1]
                    if campo_index < len(data) and data[campo_index] == valor_buscado:
                        resultados.append((RID(page_id, slot_id), data))
        return resultados



